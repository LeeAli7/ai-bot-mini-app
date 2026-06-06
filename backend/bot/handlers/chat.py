import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from db.models import Provider, User, Message as DbMessage
from bot.handlers.common import get_or_create_user
from services.ai_client import send_message, send_message_stream

logger = logging.getLogger(__name__)
router = Router()
_cancel_flags: dict[int, bool] = {}


async def get_active_provider(session: AsyncSession, user_id: int) -> Provider | None:
    result = await session.execute(
        select(Provider).where(
            and_(Provider.user_id == user_id, Provider.is_active == True)
        )
    )
    return result.scalar_one_or_none()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    _cancel_flags[message.from_user.id] = True
    await message.answer("Генерация отменена.")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
    provider = await get_active_provider(session, user.id)

    if not provider:
        await message.answer(
            "У тебя нет активного провайдера. Добавь провайдера в Mini App или через /providers."
        )
        return

    # Get history
    result = await session.execute(
        select(DbMessage)
        .where(
            and_(
                DbMessage.user_id == user.id,
                DbMessage.provider_id == provider.id,
            )
        )
        .order_by(DbMessage.created_at.desc())
        .limit(provider.context_length)
    )
    history = list(reversed(result.scalars().all()))

    status_msg = await message.answer("⏳ Думаю...")

    _cancel_flags.pop(message.from_user.id, None)
    full_reply = ""

    try:
        async for content, reasoning in send_message_stream(provider, history, message.text):
            if _cancel_flags.get(message.from_user.id):
                full_reply += "\n\n[Генерация отменена]"
                break
            full_reply += content

        if not full_reply.startswith("⚠️"):
            from db.queries import save_messages
            await save_messages(session, user.id, provider.id, message.text, full_reply)

        # Send reply
        if len(full_reply) <= 4000:
            await status_msg.edit_text(full_reply)
        else:
            await status_msg.delete()
            for i in range(0, len(full_reply), 4000):
                await message.answer(full_reply[i:i + 4000])
    except Exception as e:
        await status_msg.edit_text(f"⚠️ Ошибка: {e}")
    finally:
        _cancel_flags.pop(message.from_user.id, None)
