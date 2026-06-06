import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models import GroupSetting
from bot.handlers.common import get_or_create_user

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("public"))
async def cmd_public(message: Message, session: AsyncSession):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Эта команда доступна только в группах.")
        return

    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)

    result = await session.execute(
        select(GroupSetting).where(
            GroupSetting.user_id == user.id,
            GroupSetting.chat_id == message.chat.id,
        )
    )
    setting = result.scalar_one_or_none()

    if setting is None:
        setting = GroupSetting(user_id=user.id, chat_id=message.chat.id, public_mode=True)
        session.add(setting)
    else:
        setting.public_mode = not setting.public_mode

    await session.commit()
    status = "включен" if setting.public_mode else "выключен"
    await message.answer(f"Публичный режим {status}.")
