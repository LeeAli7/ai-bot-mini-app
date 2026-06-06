import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import BOT_TOKEN, STATIC_DIR, WEBHOOK_URL, WEBHOOK_PATH
from db.engine import init_db, AsyncSessionFactory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized")

    from services.crypto import init_crypto
    from config import get_encryption_key, ensure_workspaces_dir

    enc_key = get_encryption_key()
    init_crypto(enc_key)

    ensure_workspaces_dir()

    from services.vibe import cleanup_orphans
    cleanup_orphans()

    # Setup bot username (must happen before first webhook update)
    from aiogram import Bot
    bot = Bot(token=BOT_TOKEN)
    bot_info = await bot.get_me()
    from bot.bot_app import set_bot_username
    set_bot_username(bot_info.username)
    logger.info("Bot username: @%s", bot_info.username)

    # Setup bot webhook
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
        await bot.set_webhook(webhook_url)
        logger.info(f"Webhook set to {webhook_url}")

    # Setup Telegram Menu Button (opens Mini App)
    if WEBHOOK_URL:
        from aiogram.types import MenuButtonWebApp, WebAppInfo
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть",
                web_app=WebAppInfo(url=WEBHOOK_URL.rstrip('/'))
            )
        )
        logger.info("Menu button set to Mini App URL: %s", WEBHOOK_URL)

    await bot.session.close()

    yield

    # Shutdown
    if WEBHOOK_URL:
        from aiogram import Bot
        bot = Bot(token=BOT_TOKEN)
        await bot.delete_webhook()
        logger.info("Webhook deleted")
        await bot.session.close()


app = FastAPI(title="AI Bot Mini App", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
from api.auth import router as auth_router
from api.chat import router as chat_router
from api.providers import router as providers_router
from api.projects import router as projects_router
from api.files import router as files_router
from api.multimodal import router as multimodal_router
from api.settings import router as settings_router
from api.terminal import router as terminal_router

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(providers_router)
app.include_router(projects_router)
app.include_router(files_router)
app.include_router(multimodal_router)
app.include_router(settings_router)
app.include_router(terminal_router)

# Bot webhook
from bot.webhook import setup_webhook
setup_webhook(app)

# Static files (frontend) — serve CSS/JS at /css/ and /js/ paths
frontend_path = Path(str(STATIC_DIR))
if frontend_path.exists():
    css_path = frontend_path / "css"
    js_path = frontend_path / "js"
    if css_path.exists():
        app.mount("/css", StaticFiles(directory=str(css_path)), name="css")
    if js_path.exists():
        app.mount("/js", StaticFiles(directory=str(js_path)), name="js")

    from fastapi.responses import FileResponse

    @app.get("/")
    async def index():
        return FileResponse(str(frontend_path / "index.html"))

    logger.info(f"Static files configured from {frontend_path}")
else:
    @app.get("/")
    async def root():
        return {"message": "AI Bot Mini App API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
