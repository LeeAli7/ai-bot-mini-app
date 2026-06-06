import os

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.engine import get_db
from db.models import Project, User
from services.vibe import (
    delete_file as svc_delete_file,
    get_project_path,
    list_all_files,
)

router = APIRouter(prefix="/api/projects/{project_id}/files", tags=["files"])


async def _get_project(project_id: int, user_id: int, session: AsyncSession) -> Project:
    result = await session.execute(
        select(Project).where(
            and_(Project.id == project_id, Project.user_id == user_id)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("")
async def list_files(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user.id, session)
    project_path = str(get_project_path(user.id, project.name))
    files = list_all_files(project_path)
    return {"files": files}


@router.get("/content")
async def get_file_content(
    project_id: int,
    path: str = Query(..., description="Relative path within project"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user.id, session)
    project_path = str(get_project_path(user.id, project.name))

    from pathlib import Path
    root = Path(project_path).resolve()
    file_path = (root / path.lstrip("/")).resolve()

    if not str(file_path).startswith(str(root)):
        raise HTTPException(status_code=403, detail="Path traversal denied")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    return {"path": path, "content": content}


class FileWrite(BaseModel):
    content: str


@router.post("/{file_path:path}")
async def write_file(
    project_id: int,
    file_path: str,
    body: FileWrite,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user.id, session)
    project_path = str(get_project_path(user.id, project.name))

    from pathlib import Path
    root = Path(project_path).resolve()
    target = (root / file_path.lstrip("/")).resolve()

    if not str(target).startswith(str(root)):
        raise HTTPException(status_code=403, detail="Path traversal denied")

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(body.content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write: {e}")

    return {"path": file_path, "status": "saved"}


@router.delete("/{file_path:path}")
async def delete_file(
    project_id: int,
    file_path: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user.id, session)
    project_path = str(get_project_path(user.id, project.name))

    ok = svc_delete_file(project_path, file_path.lstrip("/"))
    if not ok:
        raise HTTPException(status_code=404, detail="File not found or path denied")
    return {"status": "deleted"}


@router.post("/upload")
async def upload_file(
    project_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user.id, session)
    project_path = str(get_project_path(user.id, project.name))

    from pathlib import Path
    root = Path(project_path).resolve()
    filename = file.filename or "uploaded_file"
    target = (root / filename).resolve()

    if not str(target).startswith(str(root)):
        raise HTTPException(status_code=403, detail="Path traversal denied")

    content = await file.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    return {"path": filename, "status": "uploaded"}


@router.get("/{file_path:path}/download")
async def download_file(
    project_id: int,
    file_path: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user.id, session)
    project_path = str(get_project_path(user.id, project.name))

    from pathlib import Path
    root = Path(project_path).resolve()
    target = (root / file_path.lstrip("/")).resolve()

    if not str(target).startswith(str(root)):
        raise HTTPException(status_code=403, detail="Path traversal denied")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(target), filename=target.name)
