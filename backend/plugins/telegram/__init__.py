"""
Telegram Plugin — connects GPS to Telegram via polling bot.

Requires GPS_TELEGRAM_TOKEN env var.
"""

import logging

logger = logging.getLogger(__name__)

PLUGIN_ID = "telegram"

_bridge = None


def get_agents() -> list:
    return []


def get_tools() -> list:
    return []


def init_db(conn) -> None:
    """Create platform_messages table for Telegram message logging."""
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS platform_messages (
        id TEXT PRIMARY KEY,
        platform TEXT NOT NULL,
        platform_msg_id TEXT,
        platform_user_id TEXT,
        platform_channel TEXT,
        direction TEXT NOT NULL,
        content TEXT,
        created_at REAL NOT NULL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_platform_messages_platform ON platform_messages(platform)')
    conn.commit()


async def start(agent_core) -> None:
    """Start the Telegram bot bridge."""
    global _bridge
    import os
    token = os.environ.get("GPS_TELEGRAM_TOKEN", "")
    if not token:
        logger.info("Telegram plugin: GPS_TELEGRAM_TOKEN not set, skipping")
        return

    try:
        from plugins.telegram.bot import TelegramBridge
        _bridge = TelegramBridge(token, agent_core)
        await _bridge.start()
        logger.info("Telegram plugin started")
    except Exception as e:
        logger.error("Telegram plugin start failed: %s", e)


async def stop() -> None:
    """Stop the Telegram bot bridge."""
    global _bridge
    if _bridge:
        await _bridge.stop()
        _bridge = None
    logger.info("Telegram plugin stopped")
