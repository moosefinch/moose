"""
SlackBridge — connects Moose to Slack using slack-bolt with AsyncSocketModeHandler.

Listens for app_mention and DM message events.
Routes through agent_core.chat(), responds in originating channel/DM.
"""

import asyncio
import logging
import sqlite3
import time
import uuid

logger = logging.getLogger(__name__)


class SlackBridge:
    def __init__(self, bot_token: str, app_token: str, agent_core):
        self._bot_token = bot_token
        self._app_token = app_token
        self._core = agent_core
        self._app = None
        self._handler = None
        self._task = None

    async def start(self):
        """Start the Slack Socket Mode handler."""
        from slack_bolt.async_app import AsyncApp
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

        self._app = AsyncApp(token=self._bot_token)

        # Listen for app mentions
        @self._app.event("app_mention")
        async def handle_mention(event, say):
            await self._on_message(event, say)

        # Listen for DM messages
        @self._app.event("message")
        async def handle_message(event, say):
            # Only handle DMs (channel_type == "im") to avoid responding to all channel messages
            if event.get("channel_type") == "im":
                await self._on_message(event, say)

        self._handler = AsyncSocketModeHandler(self._app, self._app_token)
        self._task = asyncio.create_task(self._handler.start_async())
        logger.info("SlackBridge started with Socket Mode")

    async def stop(self):
        """Stop the Slack handler."""
        if self._handler:
            try:
                await self._handler.close_async()
            except Exception as e:
                logger.error("SlackBridge stop error: %s", e)
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SlackBridge stopped")

    async def _on_message(self, event: dict, say):
        """Handle incoming Slack message."""
        text = event.get("text", "")
        user_id = event.get("user", "unknown")
        channel = event.get("channel", "unknown")
        ts = event.get("ts", "")

        # Strip bot mention from text if present
        # Slack mentions look like <@BOT_ID> at the start
        import re
        text = re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()

        if not text:
            return

        # Log incoming message
        self._log_message(
            platform="slack",
            platform_msg_id=ts,
            platform_user_id=user_id,
            platform_channel=channel,
            direction="inbound",
            content=text,
        )

        # Route through Moose agent system
        try:
            result = await self._core.chat(text, history=[])
            response = result.get("content", "Sorry, I couldn't process that.")
        except Exception as e:
            logger.error("SlackBridge chat error: %s", e)
            response = "Sorry, an error occurred while processing your message."

        # Respond in the originating channel
        try:
            await say(response[:4000])

            self._log_message(
                platform="slack",
                platform_msg_id="",
                platform_user_id="bot",
                platform_channel=channel,
                direction="outbound",
                content=response[:4000],
            )
        except Exception as e:
            logger.error("SlackBridge reply error: %s", e)

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
                (f"sl_{uuid.uuid4().hex[:12]}", platform, platform_msg_id,
                 platform_user_id, platform_channel, direction, content, time.time()),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("Failed to log platform message: %s", e)
