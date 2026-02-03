"""
Slack Plugin — connects GPS to Slack via Socket Mode.

Requires GPS_SLACK_BOT_TOKEN and GPS_SLACK_APP_TOKEN env vars.
"""

import logging

logger = logging.getLogger(__name__)

PLUGIN_ID = "slack"

_bridge = None


def get_agents() -> list:
    return []


def get_tools() -> list:
    return []


def init_db(conn) -> None:
    """Create platform_messages table for Slack message logging (shared with Telegram)."""
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
    """Start the Slack bot bridge."""
    global _bridge
    import os
    bot_token = os.environ.get("GPS_SLACK_BOT_TOKEN", "")
    app_token = os.environ.get("GPS_SLACK_APP_TOKEN", "")
    if not bot_token or not app_token:
        logger.info("Slack plugin: GPS_SLACK_BOT_TOKEN or GPS_SLACK_APP_TOKEN not set, skipping")
        return

    try:
        from plugins.slack.bot import SlackBridge
        _bridge = SlackBridge(bot_token, app_token, agent_core)
        await _bridge.start()
        logger.info("Slack plugin started")
    except Exception as e:
        logger.error("Slack plugin start failed: %s", e)


async def stop() -> None:
    """Stop the Slack bot bridge."""
    global _bridge
    if _bridge:
        await _bridge.stop()
        _bridge = None
    logger.info("Slack plugin stopped")
