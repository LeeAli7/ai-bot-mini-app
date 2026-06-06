import asyncio
import base64
import io
import httpx
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css',
    '.json', '.yaml', '.yml', '.toml', '.md', '.txt', '.sh',
    '.go', '.rs', '.java', '.c', '.cpp', '.h', '.sql',
    '.env', '.gitignore', '.dockerfile', '.xml', '.php',
    '.rb', '.swift', '.kt', '.cs', '.r', '.m',
}

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


def encode_bytes_to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode('utf-8')


def get_image_media_type(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
    }.get(ext, 'image/jpeg')


def build_vision_payload(
    messages_history: list[dict],
    user_text: str,
    image_b64: str,
    media_type: str,
) -> list[dict]:
    msgs = list(messages_history)
    msgs.append({
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{image_b64}"
                }
            },
            {
                "type": "text",
                "text": user_text or "Опиши это изображение."
            }
        ]
    })
    return msgs


async def transcribe_voice_bytes(
    audio_bytes: bytes,
    provider_base_url: str,
    provider_api_key: str,
    model: str = "whisper-1",
) -> str:
    url = f"{provider_base_url.rstrip('/')}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {provider_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers=headers,
                files={"file": ("voice.ogg", audio_bytes, "audio/ogg")},
                data={"model": model, "language": "ru"},
            )

        if response.status_code == 200:
            data = response.json()
            return data.get("text", "").strip()

        return f"⚠️ Whisper ошибка {response.status_code}: {response.text[:200]}"

    except httpx.ConnectError:
        return f"⚠️ Не удалось подключиться к Whisper API ({provider_base_url})"
    except Exception as e:
        return f"⚠️ Ошибка транскрипции: {e}"


def read_document_from_bytes(
    raw_bytes: bytes,
    file_name: str,
    mime_type: str = "",
) -> tuple[str, str]:
    ext = Path(file_name).suffix.lower()
    mime = mime_type.lower()

    is_text = ext in TEXT_EXTENSIONS or any(
        mime.startswith(t) for t in ('text/', 'application/json', 'application/xml', 'application/javascript')
    )

    if is_text:
        try:
            text = raw_bytes.decode('utf-8', errors='replace')
            if len(text) > 12000:
                text = text[:12000] + "\n\n... (файл обрезан)"
            return 'text', text
        except Exception as e:
            return 'text', f"(ошибка чтения: {e})"

    is_image = ext in IMAGE_EXTENSIONS or mime.startswith('image/')
    if is_image:
        b64 = encode_bytes_to_base64(raw_bytes)
        media_type = get_image_media_type(file_name)
        return 'image', f"{media_type}|{b64}"

    is_video = ext in {'.mp4', '.avi', '.mov', '.mkv', '.webm'} or mime.startswith('video/')
    if is_video:
        if len(raw_bytes) <= 15 * 1024 * 1024:
            b64 = encode_bytes_to_base64(raw_bytes)
            return 'video', b64
        return 'unsupported', f"видео слишком большое ({len(raw_bytes) / 1024 / 1024:.1f} MB)"

    if ext == '.gif' or mime == 'image/gif':
        b64 = encode_bytes_to_base64(raw_bytes)
        return 'image', f"image/gif|{b64}"

    if ext == '.zip' or mime in ('application/zip', 'application/x-zip-compressed'):
        return 'zip', raw_bytes

    if ext in {'.mp3', '.wav', '.ogg', '.flac', '.m4a'} or mime.startswith('audio/'):
        return 'audio', raw_bytes

    return 'unsupported', file_name


async def send_vision_request(
    provider_base_url: str,
    provider_api_key: str,
    model: str,
    system_prompt: str,
    messages: list[dict],
    temperature: float = 0.7,
) -> str:
    from services.ai_client import _retry_request

    all_messages = []
    if system_prompt:
        all_messages.append({"role": "system", "content": system_prompt})
    all_messages.extend(messages)

    headers = {
        "Authorization": f"Bearer {provider_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": all_messages,
        "temperature": temperature,
        "stream": False,
    }
    url = f"{provider_base_url.rstrip('/')}/chat/completions"

    try:
        response = await _retry_request("POST", url, json=payload, headers=headers, timeout=180.0)

        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]

        try:
            error_msg = response.json().get("error", {}).get("message", response.text)
        except Exception:
            error_msg = response.text
        return f"⚠️ Ошибка {response.status_code}: {error_msg[:300]}"

    except httpx.TimeoutException:
        logger.error("Vision request timeout for %s", provider_base_url)
        return "⚠️ Провайдер не ответил вовремя (timeout 180s)."
    except httpx.ConnectError:
        logger.error("Vision request connection failed: %s", provider_base_url)
        return f"⚠️ Не удалось подключиться к {provider_base_url}."
    except Exception as e:
        logger.exception("Vision request unexpected error for %s", provider_base_url)
        return f"⚠️ Неожиданная ошибка: {e}"


async def send_vision_request_stream(
    provider_base_url: str,
    provider_api_key: str,
    model: str,
    system_prompt: str,
    messages: list[dict],
    temperature: float = 0.7,
):
    import json as _json
    from services.ai_client import MAX_RETRIES, RETRY_BACKOFF, _should_retry

    all_messages = []
    if system_prompt:
        all_messages.append({"role": "system", "content": system_prompt})
    all_messages.extend(messages)

    headers = {
        "Authorization": f"Bearer {provider_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": all_messages,
        "temperature": temperature,
        "stream": True,
    }
    url = f"{provider_base_url.rstrip('/')}/chat/completions"

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        error_text = ""
                        async for chunk in response.aiter_text():
                            error_text += chunk
                        try:
                            error_data = _json.loads(error_text)
                            error_msg = error_data.get("error", {}).get("message", error_text)
                        except Exception:
                            error_msg = error_text[:300]
                        if _should_retry(response.status_code) and attempt < MAX_RETRIES - 1:
                            delay = RETRY_BACKOFF[attempt]
                            logger.warning(
                                "Vision stream attempt %d/%d returned %d, retrying in %ds",
                                attempt + 1, MAX_RETRIES, response.status_code, delay,
                            )
                            await asyncio.sleep(delay)
                            continue
                        yield (f"⚠️ Ошибка {response.status_code}: {error_msg}", "")
                        return

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            return

                        try:
                            chunk_data = _json.loads(data_str)
                            delta = chunk_data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            reasoning = delta.get("reasoning_content", "")
                            if content or reasoning:
                                yield (content, reasoning)
                        except (_json.JSONDecodeError, KeyError, IndexError):
                            continue
                    return

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF[attempt]
                logger.warning(
                    "Vision stream connect attempt %d/%d failed, retrying in %ds",
                    attempt + 1, MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error("Vision stream connection failed after %d attempts", MAX_RETRIES)

    if last_error:
        if isinstance(last_error, httpx.TimeoutException):
            yield ("⚠️ Провайдер не ответил вовремя (timeout 180s).", "")
        elif isinstance(last_error, httpx.ConnectError):
            yield (f"⚠️ Не удалось подключиться к {provider_base_url}.", "")
        else:
            yield (f"⚠️ Неожиданная ошибка: {last_error}", "")
