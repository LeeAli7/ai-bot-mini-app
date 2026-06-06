from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.engine import get_db
from db.models import User
from db.queries import get_active_provider
from services.multimodal import (
    build_vision_payload,
    encode_bytes_to_base64,
    get_image_media_type,
    read_document_from_bytes,
    send_vision_request,
    send_vision_request_stream,
    transcribe_voice_bytes,
)

router = APIRouter(prefix="/api", tags=["multimodal"])


async def _get_provider_for_multimodal(session, user_id):
    provider = await get_active_provider(session, user_id)
    if not provider:
        raise HTTPException(status_code=400, detail="No active provider")
    return provider


@router.post("/vision")
async def vision_request(
    image: UploadFile = File(...),
    caption: str = Form("Опиши это изображение."),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    provider = await _get_provider_for_multimodal(session, user.id)

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    raw = await image.read()
    b64 = encode_bytes_to_base64(raw)
    media_type = get_image_media_type(image.filename or "image.png")

    messages = build_vision_payload([], caption, b64, media_type)
    reply = await send_vision_request(
        provider_base_url=provider.base_url,
        provider_api_key=provider.get_api_key(),
        model=provider.model,
        system_prompt=provider.system_prompt or "",
        messages=messages,
        temperature=provider.temperature,
    )

    return {"reply": reply}


@router.post("/vision/stream")
async def vision_stream(
    image: UploadFile = File(...),
    caption: str = Form("Опиши это изображение."),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    provider = await _get_provider_for_multimodal(session, user.id)

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    raw = await image.read()
    b64 = encode_bytes_to_base64(raw)
    media_type = get_image_media_type(image.filename or "image.png")

    messages = build_vision_payload([], caption, b64, media_type)

    from fastapi.responses import StreamingResponse
    import json

    async def event_generator():
        async for content, reasoning in send_vision_request_stream(
            provider_base_url=provider.base_url,
            provider_api_key=provider.get_api_key(),
            model=provider.model,
            system_prompt=provider.system_prompt or "",
            messages=messages,
            temperature=provider.temperature,
        ):
            data = {"type": "chunk", "content": content, "reasoning": reasoning}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    provider = await _get_provider_for_multimodal(session, user.id)
    raw = await audio.read()

    text = await transcribe_voice_bytes(
        audio_bytes=raw,
        provider_base_url=provider.base_url,
        provider_api_key=provider.get_api_key(),
    )

    return {"text": text}


@router.post("/document")
async def read_document(
    document: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    raw = await document.read()
    doc_type, content = read_document_from_bytes(
        raw_bytes=raw,
        file_name=document.filename or "file",
        mime_type=document.content_type or "",
    )

    return {"type": doc_type, "content": content}
