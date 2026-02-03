"""
Blender Plugin — 3D modeling, scene manipulation, and STL export.

Provides tools for headless Blender operations (creating projects, running bpy scripts,
exporting STL for 3D printing) and GUI control (opening files in Blender).

Requires Blender to be installed. Configure blender_path in profile.yaml if
Blender is not on the default path.
"""

import logging

logger = logging.getLogger(__name__)

PLUGIN_ID = "blender"


def get_tools() -> list:
    """Return Blender tool functions."""
    from plugins.blender.tools import (
        blender_run_script,
        blender_create_project,
        blender_export_stl,
        blender_list_objects,
        blender_open_file,
    )
    return [
        blender_run_script,
        blender_create_project,
        blender_export_stl,
        blender_list_objects,
        blender_open_file,
    ]


def init_db(conn) -> None:
    """No database tables needed for Blender plugin."""
    pass


async def start(agent_core) -> None:
    """Start the Blender plugin — verify Blender is available."""
    from plugins.blender.tools import _find_blender
    blender_path = _find_blender()
    if blender_path:
        logger.info("Blender plugin started — blender at %s", blender_path)
    else:
        logger.warning("Blender plugin started — blender not found on PATH. "
                       "Set plugins.blender.blender_path in profile.yaml")


async def stop() -> None:
    """Stop the Blender plugin."""
    logger.info("Blender plugin stopped")
