"""
TelegramBridge — connects Moose to Telegram using python-telegram-bot polling.

On incoming message: routes through agent_core.chat(), sends response back.
Logs all messages to platform_messages table.
"""

import asyncio
import logging
import sqlite3
import time
import uuid

logger = logging.getLogger(__name__)


class TelegramBridge:
    def __init__(self, token: str, agent_core):
        self._token = token
        self._core = agent_core
        self._app = None
        self._task = None

    async def start(self):
        """Start polling for Telegram messages."""
        from telegram.ext import ApplicationBuilder, MessageHandler, filters

        self._app = ApplicationBuilder().token(self._token).build()
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))

        # Initialize the application (sets up bot info)
        await self._app.initialize()
        await self._app.start()

        # Start polling in background
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("TelegramBridge started polling")

    async def _poll_loop(self):
        """Run the Telegram updater polling loop."""
        try:
            updater = self._app.updater
            await updater.start_polling(drop_pending_updates=True)
            # Keep running until cancelled
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("TelegramBridge poll error: %s", e)

    async def stop(self):
        """Stop the Telegram bot."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._app:
            try:
                if self._app.updater and self._app.updater.running:
                    await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.error("TelegramBridge stop error: %s", e)
        logger.info("TelegramBridge stopped")

    async def _on_message(self, update, context):
        """Handle incoming Telegram message."""
        if not update.message or not update.message.text:
            return

        text = update.message.text
        user_id = str(update.message.from_user.id) if update.message.from_user else "unknown"
        chat_id = str(update.message.chat_id)

        # Log incoming message
        self._log_message(
            platform="telegram",
            platform_msg_id=str(update.message.message_id),
            platform_user_id=user_id,
            platform_channel=chat_id,
            direction="inbound",
            content=text,
        )

        # Route through Moose agent system
        try:
            result = await self._core.chat(text, history=[])
            response = result.get("content", "Sorry, I couldn't process that.")
        except Exception as e:
            logger.error("TelegramBridge chat error: %s", e)
            response = "Sorry, an error occurred while processing your message."

        # Send response back
        try:
            sent = await update.message.reply_text(response[:4096])

            # Log outgoing message
            self._log_message(
                platform="telegram",
                platform_msg_id=str(sent.message_id) if sent else "",
                platform_user_id="bot",
                platform_channel=chat_id,
                direction="outbound",
                content=response[:4096],
            )
        except Exception as e:
            logger.error("TelegramBridge reply error: %s", e)

    def _log_message(self, platform: str, platform_msg_id: str,
                     platform_user_id: str, platform_channel: str,
                     direction: str, content: str):
        """Log a message to the platform_messages table."""
        try:
            from tools import DB_PATH
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute(
                """INSERT OR IGNORE INTO platform_messages
                   (id, platform, platform_msg_id, platform_user_id,
                    platform_channel, direction, content, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"tg_{uuid.uuid4().hex[:12]}", platform, platform_msg_id,
                 platform_user_id, platform_channel, direction, content, time.time()),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("Failed to log platform message: %s", e)
