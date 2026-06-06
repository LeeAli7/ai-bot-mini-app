"""
Telegram bot setup using aiogram 3.x in webhook mode.
Reuses the same database session pool as the FastAPI API.
"""
import logging
from aiogram import Dispatcher

from db.engine import AsyncSessionFactory
from config import BOT_TOKEN

logger = logging.getLogger(__name__)

_dp: Dispatcher | None = None


_bot_username: str | None = None


def set_bot_username(username: str) -> None:
    """Set bot username (with @ prefix) before first webhook update."""
    global _bot_username
    _bot_username = f"@{username.lstrip('@')}"


def get_dispatcher() -> Dispatcher:
    global _dp
    if _dp is not None:
        return _dp

    # Import handlers (register themselves on the router)
    from bot.handlers.common import router as common_router
    from bot.handlers.chat import router as chat_router
    from bot.handlers.providers import router as providers_router
    from bot.handlers.group_chat import router as group_chat_router

    # Middleware imports
    from bot.middlewares.db import DbSessionMiddleware

    _dp = Dispatcher()

    # Router ordering: common → providers → chat → group_chat
    _dp.include_router(common_router)
    _dp.include_router(providers_router)
    _dp.include_router(chat_router)
    _dp.include_router(group_chat_router)

    # Middleware for DB session
    _dp.update.middleware(DbSessionMiddleware(AsyncSessionFactory))
    _dp.callback_query.middleware(DbSessionMiddleware(AsyncSessionFactory))

    # Inject bot_username (set by main.py lifespan before first webhook)
    _dp["bot_username"] = _bot_username

    logger.info("Bot dispatcher initialized (bot_username=%s)", _bot_username)
    return _dp
