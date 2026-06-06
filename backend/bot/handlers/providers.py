import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, delete

from db.models import Provider, User, Message as DbMessage
from bot.handlers.common import get_or_create_user

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("providers"))
async def cmd_providers(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)

    result = await session.execute(
        select(Provider).where(Provider.user_id == user.id).order_by(Provider.created_at.desc())
    )
    providers = result.scalars().all()

    if not providers:
        await message.answer(
            "У тебя нет провайдеров. Открой Mini App чтобы добавить провайдера "
            "через удобный интерфейс."
        )
        return

    lines = ["📡 *Твои провайдеры:*\n"]
    for p in providers:
        active = "✅" if p.is_active else "❌"
        lines.append(f"{active} *{p.name}* — {p.model}")

    await message.answer("\n".join(lines))
