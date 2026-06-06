import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.engine import get_db
from db.models import Project, Provider, User, VibeSession
from db.queries import (
    get_active_provider,
    save_messages,
    save_vibe_history,
)
from services.ai_client import send_message, send_message_stream
from services.vibe import (
    create_project_dir,
    get_project_path,
    get_project_tree,
    list_all_files,
    parse_ai_response,
    read_project_files,
    unzip_to_project,
    zip_project,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])

VIBE_SYSTEM_PROMPT = """You are an experienced programmer. When asked to write code:
1. Write complete, working code in fenced blocks with file paths.
Format: ```path/to/file.py
code here
```
2. Use DELETE to remove files: ```DELETE path/to/file.py```
3. Create all necessary files for the project to work."""


class ProjectCreate(BaseModel):
    name: str


class ProjectChatRequest(BaseModel):
    message: str


class ProjectOut(BaseModel):
    id: int
    name: str
    created_at: str
    updated_at: str


def _project_to_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("")
async def list_projects(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Project).where(Project.user_id == user.id).order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()
    return [_project_to_dict(p) for p in projects]


@router.post("")
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    path = create_project_dir(user.id, body.name)
    project = Project(user_id=user.id, name=body.name)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return _project_to_dict(project)


@router.get("/{project_id}")
async def get_project(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Project).where(
            and_(Project.id == project_id, Project.user_id == user.id)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_path = str(get_project_path(user.id, project.name))
    tree = get_project_tree(project_path)
    files = list_all_files(project_path)

    vibe_result = await session.execute(
        select(VibeSession).where(
            and_(VibeSession.project_id == project_id, VibeSession.user_id == user.id)
        ).order_by(VibeSession.updated_at.desc()).limit(1)
    )
    vibe_session = vibe_result.scalar_one_or_none()

    return {
        **_project_to_dict(project),
        "file_tree": tree,
        "files": files,
        "has_active_session": vibe_session is not None,
    }


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Project).where(
            and_(Project.id == project_id, Project.user_id == user.id)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete vibe sessions
    await session.execute(
        delete(VibeSession).where(VibeSession.project_id == project_id)
    )

    # Remove project directory
    import shutil
    project_path = get_project_path(user.id, project.name)
    if project_path.exists():
        shutil.rmtree(project_path, ignore_errors=True)

    await session.delete(project)
    await session.commit()
    return {"status": "deleted"}


@router.get("/{project_id}/zip")
async def download_project_zip(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Project).where(
            and_(Project.id == project_id, Project.user_id == user.id)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_path = str(get_project_path(user.id, project.name))
    zip_path = zip_project(project_path, project.name)
    return FileResponse(zip_path, filename=f"{project.name}.zip")


@router.post("/import-zip")
async def import_zip_project(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    import tempfile

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    # Extract name from zip filename
    project_name = file.filename.replace(".zip", "")[:255]
    project_path = create_project_dir(user.id, project_name)

    # Save to temp and extract
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    try:
        content = await file.read()
        tmp.write(content)
        tmp.close()

        extracted = unzip_to_project(tmp.name, str(project_path))
        os.unlink(tmp.name)
    except Exception as e:
        os.unlink(tmp.name)
        raise HTTPException(status_code=400, detail=f"Failed to extract: {e}")

    project = Project(user_id=user.id, name=project_name)
    session.add(project)
    await session.commit()
    await session.refresh(project)

    return {**_project_to_dict(project), "extracted_files": len(extracted)}


@router.post("/{project_id}/chat")
async def project_chat(
    project_id: int,
    body: ProjectChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Project).where(
            and_(Project.id == project_id, Project.user_id == user.id)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    provider = await get_active_provider(session, user.id)
    if not provider:
        raise HTTPException(status_code=400, detail="No active provider")

    project_path = str(get_project_path(user.id, project.name))

    # Build context with project files
    files_context = read_project_files(project_path)
    file_list = list_all_files(project_path)

    system_prompt = (
        f"{VIBE_SYSTEM_PROMPT}\n\n"
        f"Current project: {project.name}\n"
        f"Existing files:\n{file_list}\n\n"
        f"File contents:\n{files_context}"
    )

    # Get or create vibe session
    vibe_result = await session.execute(
        select(VibeSession).where(
            and_(VibeSession.project_id == project_id, VibeSession.user_id == user.id)
        ).order_by(VibeSession.updated_at.desc()).limit(1)
    )
    vibe_session = vibe_result.scalar_one_or_none()

    if vibe_session is None:
        vibe_session = VibeSession(
            project_id=project_id,
            user_id=user.id,
            history_json="[]",
        )
        session.add(vibe_session)
        await session.commit()
        await session.refresh(vibe_session)

    history = json.loads(vibe_session.history_json)

    # Build messages for AI with vibe system prompt
    from services.ai_client import AIProvider, normalize_temperature

    api_key = provider.get_api_key()
    ai = AIProvider(
        base_url=provider.base_url,
        api_key=api_key,
        model=provider.model,
        system_prompt=system_prompt,
        temperature=normalize_temperature(provider.temperature),
        context_length=provider.context_length,
    )

    reply = await ai.generate_response(body.message, history)

    if not reply.startswith("⚠️"):
        display_text, created_files = parse_ai_response(reply, project_path)
        await save_vibe_history(session, vibe_session, body.message, reply)
    else:
        display_text = reply
        created_files = []

    return {
        "reply": display_text,
        "created_files": created_files,
    }


@router.get("/{project_id}/chat/stream")
async def project_chat_stream(
    project_id: int,
    message: str = Query(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Project).where(
            and_(Project.id == project_id, Project.user_id == user.id)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    provider = await get_active_provider(session, user.id)
    if not provider:
        raise HTTPException(status_code=400, detail="No active provider")

    project_path = str(get_project_path(user.id, project.name))
    files_context = read_project_files(project_path)
    file_list = list_all_files(project_path)

    system_prompt = (
        f"{VIBE_SYSTEM_PROMPT}\n\n"
        f"Current project: {project.name}\n"
        f"Existing files:\n{file_list}\n\n"
        f"File contents:\n{files_context}"
    )

    vibe_result = await session.execute(
        select(VibeSession).where(
            and_(VibeSession.project_id == project_id, VibeSession.user_id == user.id)
        ).order_by(VibeSession.updated_at.desc()).limit(1)
    )
    vibe_session = vibe_result.scalar_one_or_none()

    if vibe_session is None:
        vibe_session = VibeSession(
            project_id=project_id,
            user_id=user.id,
            history_json="[]",
        )
        session.add(vibe_session)
        await session.commit()
        await session.refresh(vibe_session)

    history = json.loads(vibe_session.history_json)

    from services.ai_client import AIProvider, normalize_temperature

    api_key = provider.get_api_key()
    ai = AIProvider(
        base_url=provider.base_url,
        api_key=api_key,
        model=provider.model,
        system_prompt=system_prompt,
        temperature=normalize_temperature(provider.temperature),
        context_length=provider.context_length,
    )

    async def event_generator():
        full_reply = ""
        try:
            async for content, reasoning in ai.generate_response_stream(message, history):
                data = {"type": "chunk", "content": content, "reasoning": reasoning}
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                full_reply += content

            if not full_reply.startswith("⚠️"):
                display_text, created_files = parse_ai_response(full_reply, project_path)
                await save_vibe_history(session, vibe_session, message, full_reply)
                yield f"data: {json.dumps({'type': 'files', 'files': created_files, 'display': display_text}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
