import json
import datetime

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Message, Project, Provider, User, VibeSession


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


async def get_active_provider(session: AsyncSession, user_id: int) -> Provider | None:
    result = await session.execute(
        select(Provider).where(
            and_(Provider.user_id == user_id, Provider.is_active == True)
        )
    )
    return result.scalar_one_or_none()


async def get_provider_for_user(
    session: AsyncSession, provider_id: int, user_id: int
) -> Provider | None:
    result = await session.execute(
        select(Provider).where(
            and_(Provider.id == provider_id, Provider.user_id == user_id)
        )
    )
    return result.scalar_one_or_none()


async def get_chat_history(
    session: AsyncSession,
    user_id: int,
    provider_id: int,
    limit: int = 20,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(
            and_(
                Message.user_id == user_id,
                Message.provider_id == provider_id,
            )
        )
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def save_messages(
    session: AsyncSession,
    user_id: int,
    provider_id: int,
    user_text: str,
    assistant_reply: str,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    user_msg = Message(
        user_id=user_id,
        provider_id=provider_id,
        role="user",
        content=user_text,
        created_at=now,
    )
    assistant_msg = Message(
        user_id=user_id,
        provider_id=provider_id,
        role="assistant",
        content=assistant_reply,
        created_at=now,
    )
    session.add_all([user_msg, assistant_msg])
    await session.commit()


async def save_vibe_history(
    session: AsyncSession,
    vibe_session: VibeSession,
    user_text: str,
    assistant_reply: str,
) -> None:
    history = json.loads(vibe_session.history_json)
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_reply})
    vibe_session.history_json = json.dumps(history, ensure_ascii=False)
    vibe_session.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await session.commit()
