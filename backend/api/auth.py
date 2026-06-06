from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.queries import get_or_create_user
from utils.telegram_auth import validate_init_data
from utils.jwt import create_jwt

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TelegramAuthRequest(BaseModel):
    initData: str


class AuthResponse(BaseModel):
    token: str
    user: dict


@router.post("/telegram", response_model=AuthResponse)
async def auth_telegram(
    body: TelegramAuthRequest,
    session: AsyncSession = Depends(get_db),
):
    user_data = validate_init_data(body.initData)
    if not user_data:
        raise HTTPException(status_code=403, detail="Invalid initData")

    tg_id = user_data["id"]
    username = user_data.get("username")

    user = await get_or_create_user(session, tg_id, username)

    token = create_jwt(user.id, tg_id)

    return AuthResponse(
        token=token,
        user={
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "show_reasoning": user.show_reasoning,
        },
    )
