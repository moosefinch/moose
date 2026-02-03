"""
Blender tool implementations — headless Blender operations and GUI control.

Most tools run `blender -b --python <script>` with a generated bpy script.
For GUI operations, osascript is used to open files in the running Blender.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).parent.parent.parent
WORKSPACE_DIR = (BACKEND_DIR / "workspace").resolve()
SCRIPTS_DIR = Path(__file__).parent / "scripts"

# Default Blender paths (macOS)
_BLENDER_PATHS = [
    "/Applications/Blender.app/Contents/MacOS/Blender",
    "/Applications/Blender.app/Contents/MacOS/blender",
]

_blender_path_override = None


def _find_blender() -> str:
    """Find the Blender executable. Returns path or empty string."""
    if _blender_path_override:
        return _blender_path_override

    # Check profile config
    try:
        from profile import get_profile
        profile = get_profile()
        plugin_cfg = getattr(profile.plugins, "blender", None)
        if plugin_cfg and hasattr(plugin_cfg, "blender_path") and plugin_cfg.blender_path:
            if Path(plugin_cfg.blender_path).exists():
                return plugin_cfg.blender_path
    except Exception:
        pass

    # Check PATH
    try:
        result = subprocess.run(
            ["which", "blender"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    # Check known macOS paths
    for p in _BLENDER_PATHS:
        if Path(p).exists():
            return p

    return ""


def _run_blender_script(script: str, blend_file: str = "",
                        timeout: int = 60) -> tuple[int, str, str]:
    """Run a bpy Python script in Blender headless mode.

    Returns (exit_code, stdout, stderr).
    """
    blender = _find_blender()
    if not blender:
        return (-1, "", "Error: Blender not found. Install Blender or set "
                "plugins.blender.blender_path in profile.yaml")

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    # Write script to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", dir=str(WORKSPACE_DIR),
        delete=False, prefix="blender_script_",
    ) as f:
        f.write(script)
        script_path = f.name

    try:
        cmd = [blender, "-b"]
        if blend_file:
            resolved = Path(blend_file).resolve()
            if resolved.exists():
                cmd.append(str(resolved))
            else:
                return (-1, "", f"Error: blend file not found: {blend_file}")
        cmd.extend(["--python", script_path])

        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=str(WORKSPACE_DIR),
        )
        return (result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (-1, "", f"Timeout: Blender script exceeded {timeout}s")
    except Exception as e:
        return (-1, "", f"Error running Blender: {e}")
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def blender_run_script(script: str, blend_file: str = "",
                       timeout: int = 60) -> str:
    """Run a bpy Python script in Blender's headless mode. The script has full access to the bpy module. If blend_file is provided, opens that file first. Use this for custom Blender operations not covered by other tools.

    Args:
        script: Python script using bpy (Blender's Python API).
        blend_file: Optional path to a .blend file to open before running the script.
        timeout: Execution timeout in seconds (default 60).
    """
    exit_code, stdout, stderr = _run_blender_script(script, blend_file, timeout)

    output_parts = []
    if stdout:
        # Filter Blender's verbose startup output
        useful_lines = [
            line for line in stdout.splitlines()
            if not line.startswith("Blender ") and
               not line.startswith("Read prefs:") and
               not line.startswith("found bundled")
        ]
        if useful_lines:
            output_parts.append("\n".join(useful_lines[-100:]))
    if stderr:
        output_parts.append(f"STDERR:\n{stderr[-5000:]}")
    output_parts.append(f"EXIT_CODE: {exit_code}")

    return "\n".join(output_parts) or f"EXIT_CODE: {exit_code}\n(no output)"


def blender_create_project(name: str, path: str = "") -> str:
    """Create a new Blender project (.blend file) with the default scene (cube, camera, light). Saves to the specified path or workspace/<name>.blend.

    Args:
        name: Project name (used as filename if no path given).
        path: Optional full path for the .blend file.
    """
    if not path:
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        path = str(WORKSPACE_DIR / f"{name}.blend")

    # Ensure parent directory exists
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)

    script = f"""
import bpy
# Save the default scene as a new project
bpy.ops.wm.save_as_mainfile(filepath=r"{path}")
print(f"PROJECT_CREATED: {path}")
"""
    exit_code, stdout, stderr = _run_blender_script(script)

    if exit_code == 0 and Path(path).exists():
        return f"Created Blender project: {path}"
    else:
        error = stderr[-2000:] if stderr else "(no error output)"
        return f"Error creating project: {error}"


def blender_export_stl(blend_file: str, output_path: str = "",
                       object_name: str = "") -> str:
    """Export mesh from a .blend file to STL format for 3D printing. If object_name is given, exports only that object; otherwise exports all mesh objects.

    Args:
        blend_file: Path to the .blend file to export from.
        output_path: Output .stl file path. Defaults to same directory as blend_file.
        object_name: Optional specific object name to export.
    """
    blend_path = Path(blend_file).resolve()
    if not blend_path.exists():
        return f"Error: blend file not found: {blend_file}"

    if not output_path:
        output_path = str(blend_path.with_suffix(".stl"))

    # Ensure parent directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if object_name:
        script = f"""
import bpy
# Deselect all, then select target object
bpy.ops.object.select_all(action='DESELECT')
obj = bpy.data.objects.get("{object_name}")
if obj is None:
    print("ERROR: Object '{object_name}' not found")
    import sys
    sys.exit(1)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.export_mesh.stl(filepath=r"{output_path}", use_selection=True)
print(f"EXPORTED: {output_path}")
"""
    else:
        script = f"""
import bpy
# Select all mesh objects
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        obj.select_set(True)
bpy.ops.export_mesh.stl(filepath=r"{output_path}", use_selection=True)
print(f"EXPORTED: {output_path}")
"""
    exit_code, stdout, stderr = _run_blender_script(script, str(blend_path))

    if exit_code == 0 and Path(output_path).exists():
        size = Path(output_path).stat().st_size
        return f"Exported STL: {output_path} ({size} bytes)"
    else:
        error = stderr[-2000:] if stderr else stdout[-2000:] if stdout else "(no output)"
        return f"Error exporting STL: {error}"


def blender_list_objects(blend_file: str) -> str:
    """List all objects in a .blend file with their types, locations, and dimensions.

    Args:
        blend_file: Path to the .blend file to inspect.
    """
    blend_path = Path(blend_file).resolve()
    if not blend_path.exists():
        return f"Error: blend file not found: {blend_file}"

    script = """
import bpy
import json

objects = []
for obj in bpy.data.objects:
    info = {
        "name": obj.name,
        "type": obj.type,
        "location": [round(v, 4) for v in obj.location],
        "dimensions": [round(v, 4) for v in obj.dimensions],
        "visible": obj.visible_get(),
    }
    if obj.type == 'MESH' and obj.data:
        info["vertices"] = len(obj.data.vertices)
        info["faces"] = len(obj.data.polygons)
    objects.append(info)

print("OBJECTS_JSON:" + json.dumps(objects, indent=2))
"""
    exit_code, stdout, stderr = _run_blender_script(script, str(blend_path))

    if exit_code == 0 and "OBJECTS_JSON:" in stdout:
        json_str = stdout.split("OBJECTS_JSON:")[1].strip()
        return json_str
    else:
        error = stderr[-2000:] if stderr else "(no output)"
        return f"Error listing objects: {error}"


def blender_open_file(path: str) -> str:
    """Open a .blend file in the running Blender GUI application (macOS). Launches Blender if not already running.

    Args:
        path: Path to the .blend file to open.
    """
    resolved = Path(path).resolve()
    if not resolved.exists():
        return f"Error: file not found: {path}"
    if resolved.suffix.lower() != ".blend":
        return f"Error: not a .blend file: {path}"

    try:
        result = subprocess.run(
            ["open", "-a", "Blender", str(resolved)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return f"Opened {resolved.name} in Blender"
        else:
            return f"Error opening in Blender: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Timeout opening Blender"
    except Exception as e:
        return f"Error: {e}"
