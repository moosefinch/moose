"""
Plugin system — discover and load optional feature plugins.

Plugins are directories under plugins/ with an __init__.py that exports:
  - PLUGIN_ID: str
  - get_agents() -> list  (optional)
  - get_tools() -> list   (optional)
  - get_router() -> FastAPI APIRouter  (optional)
  - init_db(conn) -> None  (optional)
  - start(agent_core) -> None  (optional, async)
  - stop() -> None  (optional, async)

Each plugin may also have a plugin.json manifest for marketplace discovery.
"""

import importlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_loaded_plugins: dict[str, object] = {}
_plugins_dir = Path(__file__).parent


def discover_plugins() -> list[str]:
    """Scan the plugins directory for available plugins."""
    found = []
    for child in _plugins_dir.iterdir():
        if child.is_dir() and (child / "__init__.py").exists():
            name = child.name
            if name.startswith("_"):
                continue
            found.append(name)
    return sorted(found)


def load_plugin(name: str) -> Optional[object]:
    """Import and return a plugin module. Returns None on failure."""
    if name in _loaded_plugins:
        return _loaded_plugins[name]

    try:
        module = importlib.import_module(f"plugins.{name}")
        plugin_id = getattr(module, "PLUGIN_ID", name)
        _loaded_plugins[plugin_id] = module
        logger.info("Plugin loaded: %s", plugin_id)
        return module
    except Exception as e:
        logger.error("Failed to load plugin '%s': %s", name, e)
        return None


def get_loaded_plugins() -> dict[str, object]:
    """Return all currently loaded plugin modules."""
    return dict(_loaded_plugins)


def load_enabled_plugins(enabled_names: list[str]) -> list[object]:
    """Load all plugins that are in the enabled list."""
    loaded = []
    available = discover_plugins()
    for name in enabled_names:
        if name in available:
            plugin = load_plugin(name)
            if plugin:
                loaded.append(plugin)
        else:
            logger.warning("Plugin '%s' is enabled but not found in plugins/", name)
    return loaded


def get_plugin_manifest(name: str) -> Optional[dict]:
    """Read plugin.json manifest for a plugin. Returns None if not found."""
    manifest_path = _plugins_dir / name / "plugin.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read plugin.json for '%s': %s", name, e)
        return None


def get_plugin_manifests() -> list[dict]:
    """Read plugin.json from each discovered plugin directory."""
    manifests = []
    for name in discover_plugins():
        manifest = get_plugin_manifest(name)
        if manifest:
            manifest["_installed"] = True
            manifest["_loaded"] = name in _loaded_plugins
            manifests.append(manifest)
        else:
            # Fallback: generate basic info from module
            manifests.append({
                "id": name,
                "name": name,
                "version": "0.0.0",
                "description": "",
                "_installed": True,
                "_loaded": name in _loaded_plugins,
                "_no_manifest": True,
            })
    return manifests


def install_plugin(url: str) -> dict:
    """Install a plugin by git-cloning it into the plugins directory.

    Args:
        url: Git repository URL to clone.

    Returns:
        dict with status and plugin name.
    """
    # Extract repo name from URL for the directory name
    repo_name = url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    target_dir = _plugins_dir / repo_name
    if target_dir.exists():
        return {"error": f"Plugin directory '{repo_name}' already exists", "name": repo_name}

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(target_dir)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return {"error": f"Git clone failed: {result.stderr.strip()}", "name": repo_name}

        # Validate: must have __init__.py
        if not (target_dir / "__init__.py").exists():
            # Clean up invalid plugin
            import shutil
            shutil.rmtree(target_dir, ignore_errors=True)
            return {"error": "Cloned repo is not a valid plugin (no __init__.py)", "name": repo_name}

        manifest = get_plugin_manifest(repo_name)
        return {
            "status": "installed",
            "name": repo_name,
            "manifest": manifest,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Git clone timed out", "name": repo_name}
    except Exception as e:
        return {"error": str(e), "name": repo_name}


def remove_plugin(name: str) -> bool:
    """Remove a plugin directory. Returns True on success."""
    target_dir = _plugins_dir / name
    if not target_dir.exists() or not target_dir.is_dir():
        return False

    # Don't allow removing built-in plugins
    if name in ("crm", "telegram", "slack"):
        return False

    try:
        import shutil
        shutil.rmtree(target_dir)
        # Remove from loaded plugins cache
        _loaded_plugins.pop(name, None)
        return True
    except Exception as e:
        logger.error("Failed to remove plugin '%s': %s", name, e)
        return False
