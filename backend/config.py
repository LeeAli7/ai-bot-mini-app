import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required")

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///bot.db",
)

ENCRYPTION_SECRET_KEY = os.getenv("ENCRYPTION_SECRET_KEY", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    raise ValueError("JWT_SECRET is required")

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7

GROUP_TARGET_NAMES = os.getenv("GROUP_TARGET_NAMES", "jack,ken")

WORKSPACES_DIR = Path(os.getenv("WORKSPACES_DIR", "workspaces"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PATH = "/webhook"

STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend"


def get_encryption_key() -> str:
    if ENCRYPTION_SECRET_KEY:
        return ENCRYPTION_SECRET_KEY

    key_file = Path(__file__).resolve().parent / ".crypto_key"
    if key_file.exists():
        return key_file.read_text().strip()

    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    key_file.write_text(key)
    return key


def ensure_workspaces_dir() -> None:
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
