"""
3D Printing Plugin (Bambu Labs) — printer control via MQTT and FTPS.

Provides tools for monitoring printer status, uploading files, starting/stopping
prints, and listing files on the printer's SD card.

Requires a Bambu Labs printer with Developer Mode enabled.
Configure printer IP, access code, and serial in profile.yaml.
"""

import logging

logger = logging.getLogger(__name__)

PLUGIN_ID = "printing"

_mqtt_client = None


def get_tools() -> list:
    """Return 3D printing tool functions."""
    from plugins.printing.tools import (
        printer_status,
        printer_upload,
        printer_start,
        printer_stop,
        printer_list_files,
    )
    return [
        printer_status,
        printer_upload,
        printer_start,
        printer_stop,
        printer_list_files,
    ]


def init_db(conn) -> None:
    """Create print job tracking table."""
    conn.execute('''CREATE TABLE IF NOT EXISTS print_jobs (
        id TEXT PRIMARY KEY,
        file_name TEXT,
        status TEXT DEFAULT 'uploaded',
        started_at REAL,
        completed_at REAL,
        progress REAL DEFAULT 0,
        notes TEXT
    )''')
    conn.commit()


async def start(agent_core) -> None:
    """Start the printing plugin — connect MQTT for status monitoring."""
    global _mqtt_client
    try:
        from plugins.printing.mqtt_client import BambuMQTTClient
        from profile import get_profile

        profile = get_profile()
        plugin_cfg = getattr(profile.plugins, "printing", None)

        if not plugin_cfg:
            logger.warning("Printing plugin: no config found in profile.yaml")
            return

        ip = getattr(plugin_cfg, "printer_ip", "")
        access_code = getattr(plugin_cfg, "access_code", "")
        serial = getattr(plugin_cfg, "serial", "")

        if not ip or not access_code:
            logger.warning("Printing plugin: printer_ip and access_code required in profile.yaml")
            return

        _mqtt_client = BambuMQTTClient(
            host=ip,
            access_code=access_code,
            serial=serial,
        )
        await _mqtt_client.connect()
        logger.info("Printing plugin started — connected to printer at %s", ip)

    except ImportError as e:
        logger.warning("Printing plugin: missing dependency: %s. "
                       "Install paho-mqtt: pip install paho-mqtt", e)
    except Exception as e:
        logger.error("Printing plugin start failed: %s", e)


async def stop() -> None:
    """Stop the printing plugin — disconnect MQTT."""
    global _mqtt_client
    if _mqtt_client:
        await _mqtt_client.disconnect()
        _mqtt_client = None
    logger.info("Printing plugin stopped")


def get_mqtt_client():
    """Return the active MQTT client (used by tools)."""
    return _mqtt_client
