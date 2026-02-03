"""Plugin marketplace/discovery endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import verify_api_key

router = APIRouter()


class InstallPluginRequest(BaseModel):
    url: str


@router.get("/api/plugins", dependencies=[Depends(verify_api_key)])
async def list_plugins():
    """List all discovered plugins with their manifests."""
    from plugins import get_plugin_manifests
    return get_plugin_manifests()


@router.get("/api/plugins/{plugin_id}", dependencies=[Depends(verify_api_key)])
async def get_plugin(plugin_id: str):
    """Get a single plugin's manifest and status."""
    from plugins import get_plugin_manifest, discover_plugins, get_loaded_plugins
    if plugin_id not in discover_plugins():
        raise HTTPException(status_code=404, detail="Plugin not found")
    manifest = get_plugin_manifest(plugin_id)
    loaded = get_loaded_plugins()
    return {
        **(manifest or {"id": plugin_id, "name": plugin_id}),
        "_installed": True,
        "_loaded": plugin_id in loaded,
    }


@router.post("/api/plugins/install", dependencies=[Depends(verify_api_key)])
async def install_plugin(req: InstallPluginRequest):
    """Install a plugin by git-cloning a repository URL into the plugins directory."""
    from plugins import install_plugin as do_install
    result = do_install(req.url)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/api/plugins/{plugin_id}", dependencies=[Depends(verify_api_key)])
async def remove_plugin(plugin_id: str):
    """Remove a plugin directory (not built-in plugins)."""
    from plugins import remove_plugin as do_remove
    success = do_remove(plugin_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot remove plugin (not found or built-in)")
    return {"status": "removed", "id": plugin_id}
