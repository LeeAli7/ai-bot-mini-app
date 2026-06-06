from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.engine import get_db
from db.models import User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    show_reasoning: bool | None = None


@router.get("")
async def get_settings(user: User = Depends(get_current_user)):
    return {
        "show_reasoning": user.show_reasoning,
        "username": user.username,
        "telegram_id": user.telegram_id,
    }


@router.patch("")
async def update_settings(
    body: SettingsUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    if body.show_reasoning is not None:
        user.show_reasoning = body.show_reasoning
        await session.commit()
        await session.refresh(user)

    return {
        "show_reasoning": user.show_reasoning,
        "username": user.username,
        "telegram_id": user.telegram_id,
    }
