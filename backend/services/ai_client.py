import json
import asyncio
import logging
import httpx
from db.models import Provider, Message
from dataclasses import dataclass
from typing import Optional, AsyncIterator

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = (1, 2, 4)


def _should_retry(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


async def _retry_request(method: str, url: str, **kwargs) -> httpx.Response:
    last_exc = None
    timeout = kwargs.pop("timeout", 180.0)
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, **kwargs)
            if _should_retry(response.status_code) and attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF[attempt]
                logger.warning(
                    "Request attempt %d/%d to %s returned %d, retrying in %ds",
                    attempt + 1, MAX_RETRIES, url, response.status_code, delay,
                )
                await asyncio.sleep(delay)
                continue
            return response
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_exc = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF[attempt]
                logger.warning(
                    "Request attempt %d/%d to %s failed (%s), retrying in %ds",
                    attempt + 1, MAX_RETRIES, url, type(e).__name__, delay,
                )
                await asyncio.sleep(delay)
            else:
                raise
    if last_exc:
        raise last_exc


@dataclass
class AIProvider:
    base_url: str
    api_key: str
    model: str
    system_prompt: str = "You are a helpful AI assistant."
    temperature: float = 0.7
    context_length: int = 20

    def _build_messages(self, user_text: str, history: list = None) -> list[dict]:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        if history:
            for msg in history:
                if isinstance(msg, dict):
                    if msg.get("role") in ("user", "assistant"):
                        messages.append({"role": msg["role"], "content": msg["content"]})
                elif msg.role in ("user", "assistant"):
                    messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": user_text})
        return messages

    async def generate_response(self, user_text: str, history: list = None) -> str:
        messages = self._build_messages(user_text, history)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        try:
            response = await _retry_request("POST", url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]

            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", response.text)
            except Exception:
                error_msg = response.text

            return f"⚠️ Ошибка {response.status_code}: {error_msg}"

        except httpx.TimeoutException:
            logger.error("Timeout connecting to %s", self.base_url)
            return "⚠️ Провайдер не ответил вовремя (timeout 180s)."
        except httpx.ConnectError:
            logger.error("Connection failed to %s", self.base_url)
            return f"⚠️ Не удалось подключиться к {self.base_url}. Проверь URL."
        except Exception as e:
            logger.exception("Unexpected error calling %s", self.base_url)
            return f"⚠️ Неожиданная ошибка: {str(e)}"

    async def generate_response_stream(
        self, user_text: str, history: list = None
    ) -> AsyncIterator[tuple[str, str]]:
        messages = self._build_messages(user_text, history)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": True,
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"

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
                                error_data = json.loads(error_text)
                                error_msg = error_data.get("error", {}).get("message", error_text)
                            except Exception:
                                error_msg = error_text[:300]
                            if _should_retry(response.status_code) and attempt < MAX_RETRIES - 1:
                                delay = RETRY_BACKOFF[attempt]
                                logger.warning(
                                    "Stream request attempt %d/%d returned %d, retrying in %ds",
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
                                chunk_data = json.loads(data_str)
                                delta = chunk_data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                reasoning = delta.get("reasoning_content", "")
                                if content or reasoning:
                                    yield (content, reasoning)
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                        return

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BACKOFF[attempt]
                    logger.warning(
                        "Stream connect attempt %d/%d failed, retrying in %ds",
                        attempt + 1, MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("Stream connection failed after %d attempts", MAX_RETRIES)

        if last_error:
            if isinstance(last_error, httpx.TimeoutException):
                yield ("⚠️ Провайдер не ответил вовремя (timeout 180s).", "")
            elif isinstance(last_error, httpx.ConnectError):
                yield (f"⚠️ Не удалось подключиться к {self.base_url}. Проверь URL.", "")
            else:
                yield (f"⚠️ Ошибка подключения: {last_error}", "")


def normalize_temperature(temperature: float) -> float:
    """Convert from internal int*10 representation (7 = 0.7) to API float if needed."""
    if temperature > 2:
        return temperature / 10.0
    return float(temperature)


async def send_message(
    provider: Provider,
    history: list[Message],
    user_text: str
) -> str:
    api_key = provider.get_api_key() if hasattr(provider, 'get_api_key') else provider.api_key

    ai_provider = AIProvider(
        base_url=provider.base_url,
        api_key=api_key,
        model=provider.model,
        system_prompt=provider.system_prompt or "You are a helpful AI assistant.",
        temperature=normalize_temperature(provider.temperature),
        context_length=provider.context_length,
    )

    return await ai_provider.generate_response(user_text, history)


async def send_message_stream(
    provider: Provider,
    history: list,
    user_text: str,
) -> AsyncIterator[tuple[str, str]]:
    api_key = provider.get_api_key() if hasattr(provider, 'get_api_key') else provider.api_key

    ai_provider = AIProvider(
        base_url=provider.base_url,
        api_key=api_key,
        model=provider.model,
        system_prompt=provider.system_prompt or "You are a helpful AI assistant.",
        temperature=normalize_temperature(provider.temperature),
        context_length=provider.context_length,
    )

    async for chunk in ai_provider.generate_response_stream(user_text, history):
        yield chunk
