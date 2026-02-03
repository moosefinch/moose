"""
3D Printing tool implementations — Bambu Labs printer control.

Uses MQTT for commands/monitoring and FTPS for file upload.
"""

import ftplib
import json
import logging
import ssl
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).parent.parent.parent
WORKSPACE_DIR = (BACKEND_DIR / "workspace").resolve()


def _get_config() -> dict:
    """Get printing plugin config from profile."""
    try:
        from profile import get_profile
        profile = get_profile()
        plugin_cfg = getattr(profile.plugins, "printing", None)
        if plugin_cfg:
            return {
                "printer_ip": getattr(plugin_cfg, "printer_ip", ""),
                "access_code": getattr(plugin_cfg, "access_code", ""),
                "serial": getattr(plugin_cfg, "serial", ""),
                "ftps_port": getattr(plugin_cfg, "ftps_port", 990),
            }
    except Exception:
        pass
    return {}


def _get_mqtt():
    """Get the active MQTT client."""
    from plugins.printing import get_mqtt_client
    return get_mqtt_client()


def printer_status() -> str:
    """Get the current status of the connected Bambu Labs 3D printer. Returns temperature, progress, state, and other live data from the printer's MQTT feed."""
    mqtt = _get_mqtt()
    if not mqtt:
        return "Error: printing plugin not connected. Check profile.yaml plugins.printing configuration."

    if not mqtt.connected:
        return "Error: MQTT not connected to printer. Verify printer IP, access code, and that Developer Mode is enabled."

    status = mqtt.get_status()

    # Format for readability
    summary = {
        "state": status["gcode_state"],
        "progress": f"{status['mc_percent']}%",
        "remaining_time_min": status["mc_remaining_time"],
        "bed_temp": f"{status['bed_temper']}°C (target: {status['bed_target_temper']}°C)",
        "nozzle_temp": f"{status['nozzle_temper']}°C (target: {status['nozzle_target_temper']}°C)",
        "current_file": status["gcode_file"] or status["subtask_name"] or "(none)",
        "layer": f"{status['layer_num']}/{status['total_layer_num']}" if status["total_layer_num"] else "N/A",
        "connected": status["connected"],
    }
    return json.dumps(summary, indent=2)


def printer_upload(file_path: str) -> str:
    """Upload a .3mf or .gcode file to the Bambu Labs printer via FTPS. The file will be placed on the printer's SD card ready for printing.

    Args:
        file_path: Path to the file to upload (.3mf or .gcode).
    """
    path = Path(file_path).resolve()
    if not path.exists():
        return f"Error: file not found: {file_path}"

    suffix = path.suffix.lower()
    if suffix not in (".3mf", ".gcode", ".gcode.3mf"):
        return f"Error: unsupported file type '{suffix}'. Use .3mf or .gcode files."

    config = _get_config()
    if not config.get("printer_ip") or not config.get("access_code"):
        return "Error: printer_ip and access_code required in profile.yaml"

    try:
        # Bambu Labs uses implicit FTPS (port 990)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        ftp = ftplib.FTP_TLS(context=ctx)
        ftp.connect(config["printer_ip"], config.get("ftps_port", 990))
        ftp.login("bblp", config["access_code"])
        ftp.prot_p()  # Enable data channel encryption

        # Upload to root or sdcard directory
        remote_name = path.name
        with open(path, "rb") as f:
            ftp.storbinary(f"STOR {remote_name}", f)

        ftp.quit()

        size = path.stat().st_size
        return f"Uploaded {remote_name} ({size} bytes) to printer"

    except ftplib.all_errors as e:
        return f"FTPS upload error: {e}"
    except Exception as e:
        return f"Error uploading to printer: {e}"


def printer_start(file_name: str) -> str:
    """Start a print job on the Bambu Labs printer. The file must already be on the printer (uploaded via printer_upload).

    Args:
        file_name: Name of the file to print (as shown by printer_list_files).
    """
    mqtt = _get_mqtt()
    if not mqtt:
        return "Error: printing plugin not connected"
    if not mqtt.connected:
        return "Error: MQTT not connected to printer"

    config = _get_config()

    command = {
        "print": {
            "command": "project_file",
            "param": f"Metadata/plate_1.gcode",
            "subtask_name": file_name,
            "url": f"ftp://{config.get('printer_ip', 'printer')}/{file_name}",
            "bed_type": "auto",
            "timelapse": False,
            "bed_leveling": True,
            "flow_cali": True,
            "vibration_cali": True,
            "layer_inspect": False,
            "use_ams": False,
        }
    }

    success = mqtt.publish_command(command)
    if success:
        return f"Print job started: {file_name}"
    else:
        return "Error: failed to send print command via MQTT"


def printer_stop() -> str:
    """Stop the current print job on the Bambu Labs printer. This will halt the print immediately."""
    mqtt = _get_mqtt()
    if not mqtt:
        return "Error: printing plugin not connected"
    if not mqtt.connected:
        return "Error: MQTT not connected to printer"

    command = {
        "print": {
            "command": "stop",
        }
    }

    success = mqtt.publish_command(command)
    if success:
        return "Print stop command sent"
    else:
        return "Error: failed to send stop command via MQTT"


def printer_list_files() -> str:
    """List files on the Bambu Labs printer's SD card via FTPS. Shows available .3mf and .gcode files that can be printed."""
    config = _get_config()
    if not config.get("printer_ip") or not config.get("access_code"):
        return "Error: printer_ip and access_code required in profile.yaml"

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        ftp = ftplib.FTP_TLS(context=ctx)
        ftp.connect(config["printer_ip"], config.get("ftps_port", 990))
        ftp.login("bblp", config["access_code"])
        ftp.prot_p()

        files = []
        ftp.retrlines("LIST", lambda line: files.append(line))
        ftp.quit()

        if not files:
            return "No files found on printer"

        # Parse FTP LIST output
        parsed = []
        for line in files:
            parts = line.split(None, 8)
            if len(parts) >= 9:
                name = parts[8]
                size = parts[4]
                parsed.append(f"  {name}  ({size} bytes)")
            else:
                parsed.append(f"  {line.strip()}")

        return "Files on printer:\n" + "\n".join(parsed)

    except ftplib.all_errors as e:
        return f"FTPS error: {e}"
    except Exception as e:
        return f"Error listing printer files: {e}"
