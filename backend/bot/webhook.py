import logging
from fastapi import FastAPI, Request, Response

from config import BOT_TOKEN, WEBHOOK_PATH

logger = logging.getLogger(__name__)


def setup_webhook(app: FastAPI) -> None:
    """
    Registers the Telegram webhook endpoint on the FastAPI app.
    Lazily imports the bot dispatcher to avoid import-time side effects.
    """

    @app.post(WEBHOOK_PATH)
    async def telegram_webhook(request: Request):
        from aiogram import Bot, Dispatcher
        from aiogram.types import Update

        bot = Bot(token=BOT_TOKEN)

        # Lazy init dispatcher
        from bot.bot_app import get_dispatcher
        dp = get_dispatcher()

        try:
            update_data = await request.json()
            update = Update.model_validate(update_data)
            await dp.feed_webhook_update(bot, update)
        except Exception:
            logger.exception("Webhook processing error")

        await bot.session.close()
        return Response(status_code=200)
