import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import User

logger = logging.getLogger(__name__)
router = Router()


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, username: str | None = None
) -> User:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif username and user.username != username:
        user.username = username
        await session.commit()
    return user


@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
    await message.answer(
        "Привет! Я AI-бот.\n\n"
        "Используй Mini App для полного функционала: управление провайдерами, чат с AI, "
        "вайб-кодинг и многое другое.\n\n"
        "/help — список команд"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📋 Команды:\n"
        "/start — перезапустить бота\n"
        "/help — это сообщение\n"
        "/reasoning — переключить отображение рассуждений AI\n"
        "/providers — управление провайдерами\n"
        "/cancel — отменить генерацию\n\n"
        "🌐 Открой Mini App для расширенного интерфейса!"
    )


@router.message(Command("reasoning"))
async def cmd_reasoning(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
    user.show_reasoning = not user.show_reasoning
    await session.commit()
    status = "включены" if user.show_reasoning else "выключены"
    await message.answer(f"Рассуждения AI: {status}")
