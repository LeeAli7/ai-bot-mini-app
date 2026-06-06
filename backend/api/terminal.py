import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.engine import get_db
from db.models import Project, User
from services.vibe import (
    PTY_AVAILABLE,
    get_project_path,
    get_pty_session,
    kill_pty,
    list_active_pty,
    signal_pty,
    start_pty,
    stream_pty_output,
    write_pty,
)

router = APIRouter(prefix="/api/projects/{project_id}/terminal", tags=["terminal"])


class TerminalStart(BaseModel):
    command: str = "bash"


class TerminalInput(BaseModel):
    session_id: int = 0
    input: str


@router.post("/start")
async def terminal_start(
    project_id: int,
    body: TerminalStart = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    if not PTY_AVAILABLE:
        raise HTTPException(status_code=501, detail="PTY not available on this platform")

    result = await session.execute(
        select(Project).where(
            and_(Project.id == project_id, Project.user_id == user.id)
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_path = str(get_project_path(user.id, project.name))
    cmd = body.command if body else "bash"
    cmd_list = ["bash", "-c", cmd] if cmd != "bash" else ["bash"]

    try:
        pty_session = start_pty(user.id, 0, cmd_list, project_path, cmd)
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))

    return {
        "session_id": user.id,
        "command": cmd,
        "status": "started",
    }


@router.post("/stdin")
async def terminal_stdin(
    project_id: int,
    body: TerminalInput,
    user: User = Depends(get_current_user),
):
    ok = write_pty(user.id, body.input)
    if not ok:
        raise HTTPException(status_code=400, detail="No active terminal session")
    return {"status": "sent"}


@router.get("/output")
async def terminal_output(
    project_id: int,
    user: User = Depends(get_current_user),
):
    async def event_generator():
        async for event in stream_pty_output(user.id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/kill")
async def terminal_kill(
    project_id: int,
    body: TerminalInput,
    user: User = Depends(get_current_user),
):
    kill_pty(user.id)
    return {"status": "killed"}


@router.post("/signal")
async def terminal_signal(
    project_id: int,
    body: TerminalInput,
    user: User = Depends(get_current_user),
):
    import signal
    signal_pty(user.id, signal.SIGINT)
    return {"status": "signalled"}


@router.get("/list")
async def terminal_list(
    project_id: int,
    user: User = Depends(get_current_user),
):
    sessions = list_active_pty()
    return {
        "sessions": [
            {"user_id": s.user_id, "label": s.label, "finished": s.finished}
            for s in sessions
        ]
    }
