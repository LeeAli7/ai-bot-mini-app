import json
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.deps import get_current_user
from db.engine import get_db
from db.models import Message, Provider, User
from db.queries import get_active_provider, get_chat_history, save_messages
from services.ai_client import send_message, send_message_stream

router = APIRouter(prefix="/api/chat", tags=["chat"])

_cancel_flags: dict[int, bool] = {}


class ChatRequest(BaseModel):
    message: str
    provider_id: int | None = None


class ChatResponse(BaseModel):
    reply: str


class HistoryResponse(BaseModel):
    messages: list[dict]


@router.post("", response_model=ChatResponse)
async def chat_send(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    provider = await _resolve_provider(session, user.id, body.provider_id)
    if not provider:
        raise HTTPException(status_code=400, detail="No active provider. Add one first.")

    history = await get_chat_history(session, user.id, provider.id, provider.context_length)

    reply = await send_message(provider, history, body.message)

    if not reply.startswith("⚠️"):
        await save_messages(session, user.id, provider.id, body.message, reply)

    return ChatResponse(reply=reply)


@router.post("/cancel")
async def chat_cancel(user: User = Depends(get_current_user)):
    _cancel_flags[user.id] = True
    return {"status": "cancelled"}


@router.get("/stream")
async def chat_stream(
    message: str = Query(...),
    provider_id: int | None = Query(None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    provider = await _resolve_provider(session, user.id, provider_id)
    if not provider:
        raise HTTPException(status_code=400, detail="No active provider. Add one first.")

    history = await get_chat_history(session, user.id, provider.id, provider.context_length)

    _cancel_flags.pop(user.id, None)

    async def event_generator():
        full_reply = ""
        try:
            async for content, reasoning in send_message_stream(provider, history, message):
                if _cancel_flags.get(user.id):
                    full_reply += "\n\n[Генерация отменена]"
                    yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                    break

                data = {"type": "chunk", "content": content, "reasoning": reasoning}
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                full_reply += content
            else:
                if not full_reply.startswith("⚠️"):
                    await save_messages(session, user.id, provider.id, message, full_reply)
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            _cancel_flags.pop(user.id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history", response_model=HistoryResponse)
async def chat_history(
    provider_id: int | None = Query(None),
    limit: int = Query(20, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    provider = await _resolve_provider(session, user.id, provider_id)
    if not provider:
        return HistoryResponse(messages=[])

    messages = await get_chat_history(session, user.id, provider.id, limit)
    return HistoryResponse(
        messages=[
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in messages
        ]
    )


@router.delete("/history")
async def clear_chat_history(
    provider_id: int | None = Query(None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    provider = await _resolve_provider(session, user.id, provider_id)
    if not provider:
        raise HTTPException(status_code=400, detail="No provider specified")

    await session.execute(
        delete(Message).where(
            and_(Message.user_id == user.id, Message.provider_id == provider.id)
        )
    )
    await session.commit()
    return {"status": "cleared"}


async def _resolve_provider(
    session: AsyncSession, user_id: int, provider_id: int | None
) -> Provider | None:
    if provider_id:
        result = await session.execute(
            select(Provider).where(
                and_(Provider.id == provider_id, Provider.user_id == user_id)
            )
        )
        return result.scalar_one_or_none()
    return await get_active_provider(session, user_id)
