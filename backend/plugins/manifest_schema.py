"""
Plugin manifest schema — validates plugin.json files.
"""

from typing import Optional
from pydantic import BaseModel


class PluginManifest(BaseModel):
    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    provides: list[str] = []         # e.g. ["agents", "tools", "routes"]
    dependencies: list[str] = []     # e.g. ["python-telegram-bot>=20.0"]
    homepage: Optional[str] = None
    license: Optional[str] = None
