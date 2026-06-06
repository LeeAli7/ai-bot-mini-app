import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    show_reasoning = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    providers = relationship("Provider", back_populates="user", lazy="dynamic")
    projects = relationship("Project", back_populates="user", lazy="dynamic")
    messages = relationship("Message", back_populates="user", lazy="dynamic")


class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    base_url = Column(String(1024), nullable=False)
    api_key = Column(String(256), nullable=True)
    api_key_encrypted = Column(Text, nullable=True)
    model = Column(String(255), nullable=False, default="gpt-3.5-turbo")
    system_prompt = Column(Text, nullable=True, default="")
    temperature = Column(Integer, nullable=False, default=7)
    context_length = Column(Integer, nullable=False, default=10)
    is_active = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="providers")
    messages = relationship("Message", back_populates="provider", lazy="dynamic")

    def set_api_key(self, key: str) -> None:
        from services.crypto import crypto_service as cs

        svc = cs()
        self.api_key_encrypted = svc.encrypt(key)
        self.api_key = None

    def get_api_key(self) -> str:
        if self.api_key_encrypted:
            from services.crypto import crypto_service as cs

            return cs().decrypt(self.api_key_encrypted)
        return self.api_key or ""


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, index=True)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    chat_type = Column(String(20), nullable=True, default="dm")
    chat_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)

    user = relationship("User", back_populates="messages")
    provider = relationship("Provider", back_populates="messages")


class GroupSetting(Base):
    __tablename__ = "group_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    public_mode = Column(Boolean, default=False)


class BotResponse(Base):
    __tablename__ = "bot_responses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=False, index=True)
    message_id = Column(BigInteger, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="projects")
    vibe_sessions = relationship("VibeSession", back_populates="project", lazy="dynamic")


class VibeSession(Base):
    __tablename__ = "vibe_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    history_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="vibe_sessions")


__all__ = [
    "Base",
    "User",
    "Provider",
    "Message",
    "GroupSetting",
    "BotResponse",
    "Project",
    "VibeSession",
]
