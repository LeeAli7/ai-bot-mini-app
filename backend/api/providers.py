from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.engine import get_db
from db.models import Message, Provider, User
from services.ai_client import AIProvider

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderCreate(BaseModel):
    name: str
    base_url: str
    api_key: str
    model: str = "gpt-3.5-turbo"
    system_prompt: str = ""
    temperature: int = 7
    context_length: int = 10


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    temperature: int | None = None
    context_length: int | None = None


class ProviderOut(BaseModel):
    id: int
    name: str
    base_url: str
    model: str
    system_prompt: str | None
    temperature: int
    context_length: int
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


def _provider_to_dict(p: Provider) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "base_url": p.base_url,
        "model": p.model,
        "system_prompt": p.system_prompt,
        "temperature": p.temperature,
        "context_length": p.context_length,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("")
async def list_providers(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Provider).where(Provider.user_id == user.id).order_by(Provider.created_at.desc())
    )
    providers = result.scalars().all()
    return [_provider_to_dict(p) for p in providers]


@router.post("")
async def create_provider(
    body: ProviderCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    if len(body.api_key) < 6:
        raise HTTPException(status_code=400, detail="API key too short")

    # Count existing providers
    result = await session.execute(
        select(Provider).where(Provider.user_id == user.id)
    )
    existing = result.scalars().all()

    # First provider auto-activates
    is_active = len(existing) == 0

    provider = Provider(
        user_id=user.id,
        name=body.name,
        base_url=body.base_url,
        model=body.model,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
        context_length=body.context_length,
        is_active=is_active,
    )
    provider.set_api_key(body.api_key)
    session.add(provider)
    await session.commit()
    await session.refresh(provider)

    return _provider_to_dict(provider)


@router.get("/{provider_id}")
async def get_provider(
    provider_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Provider).where(
            and_(Provider.id == provider_id, Provider.user_id == user.id)
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return _provider_to_dict(provider)


@router.patch("/{provider_id}")
async def update_provider(
    provider_id: int,
    body: ProviderUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Provider).where(
            and_(Provider.id == provider_id, Provider.user_id == user.id)
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    update_data = body.model_dump(exclude_unset=True)
    if "api_key" in update_data:
        api_key = update_data.pop("api_key")
        if len(api_key) < 6:
            raise HTTPException(status_code=400, detail="API key too short")
        provider.set_api_key(api_key)

    for key, value in update_data.items():
        setattr(provider, key, value)

    await session.commit()
    await session.refresh(provider)
    return _provider_to_dict(provider)


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Provider).where(
            and_(Provider.id == provider_id, Provider.user_id == user.id)
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    was_active = provider.is_active

    # Delete messages for this provider
    await session.execute(
        delete(Message).where(
            and_(Message.user_id == user.id, Message.provider_id == provider_id)
        )
    )
    await session.delete(provider)
    await session.commit()

    # If was active, auto-switch to another provider
    if was_active:
        result = await session.execute(
            select(Provider).where(Provider.user_id == user.id).limit(1)
        )
        next_provider = result.scalar_one_or_none()
        if next_provider:
            next_provider.is_active = True
            await session.commit()

    return {"status": "deleted"}


@router.post("/{provider_id}/activate")
async def activate_provider(
    provider_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Provider).where(
            and_(Provider.id == provider_id, Provider.user_id == user.id)
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Deactivate all others
    await session.execute(
        update(Provider)
        .where(and_(Provider.user_id == user.id, Provider.id != provider_id))
        .values(is_active=False)
    )
    provider.is_active = True
    await session.commit()
    await session.refresh(provider)
    return _provider_to_dict(provider)


@router.post("/{provider_id}/clear-history")
async def clear_provider_history(
    provider_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Provider).where(
            and_(Provider.id == provider_id, Provider.user_id == user.id)
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    await session.execute(
        delete(Message).where(
            and_(Message.user_id == user.id, Message.provider_id == provider_id)
        )
    )
    await session.commit()
    return {"status": "cleared"}


@router.post("/{provider_id}/test")
async def test_provider_connection(
    provider_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Provider).where(
            and_(Provider.id == provider_id, Provider.user_id == user.id)
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    api_key = provider.get_api_key()
    client = AIProvider(
        base_url=provider.base_url,
        api_key=api_key,
        model=provider.model,
        system_prompt="You are helpful.",
        temperature=0.7,
        context_length=1,
    )

    reply = await client.generate_response("Say 'ok' in one word.")
    if reply.startswith("⚠️"):
        return {"status": "error", "message": reply}
    return {"status": "ok", "message": reply[:200]}
