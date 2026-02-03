"""
System scanning tools for the security heartbeat.
Internal only — not callable by agents through the tool system.

Provides process, network, and file integrity scanning for
WhiteRabbitNeo to analyze on a recurring schedule.
"""

import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def scan_processes() -> dict:
    """Run `ps aux` and return parsed process list."""
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=15,
        )
        lines = result.stdout.strip().split("\n")
        header = lines[0] if lines else ""
        processes = []
        for line in lines[1:]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                processes.append({
                    "user": parts[0],
                    "pid": parts[1],
                    "cpu": parts[2],
                    "mem": parts[3],
                    "command": parts[10],
                })
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "process_count": len(processes),
            "processes": processes,
            "raw_header": header,
        }
    except Exception as e:
        logger.error("[SystemScan] Process scan failed: %s", e)
        return {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}


def scan_network() -> dict:
    """Run `lsof -i -P -n` and `netstat -an` to return active connections."""
    connections = []

    # lsof for process-level connection info
    try:
        result = subprocess.run(
            ["lsof", "-i", "-P", "-n"],
            capture_output=True, text=True, timeout=15,
        )
        lines = result.stdout.strip().split("\n")
        for line in lines[1:]:
            parts = line.split(None, 8)
            if len(parts) >= 9:
                connections.append({
                    "command": parts[0],
                    "pid": parts[1],
                    "user": parts[2],
                    "type": parts[4],
                    "name": parts[8] if len(parts) > 8 else "",
                })
    except Exception as e:
        logger.error("[SystemScan] lsof scan failed: %s", e)

    # netstat for listening ports
    listening = []
    try:
        result = subprocess.run(
            ["netstat", "-an"],
            capture_output=True, text=True, timeout=15,
        )
        for line in result.stdout.split("\n"):
            if "LISTEN" in line or "ESTABLISHED" in line:
                listening.append(line.strip())
    except Exception as e:
        logger.error("[SystemScan] netstat scan failed: %s", e)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "connection_count": len(connections),
        "connections": connections,
        "listening_summary": listening[:100],  # cap for LLM context
    }


def scan_file_integrity(watched_paths: list[str], baseline_path: str) -> dict:
    """Checksum key directories and compare against baseline.

    Args:
        watched_paths: List of directory paths to scan.
        baseline_path: Path to the baseline JSON file.

    Returns:
        Dict with changes detected, new files, removed files, and updated baseline.
    """
    current_checksums = {}

    for dir_path in watched_paths:
        expanded = os.path.expanduser(dir_path)
        p = Path(expanded)
        if not p.exists():
            continue
        try:
            if p.is_file():
                current_checksums[str(p)] = _hash_file(p)
            elif p.is_dir():
                for f in p.iterdir():
                    if f.is_file():
                        try:
                            current_checksums[str(f)] = _hash_file(f)
                        except (PermissionError, OSError):
                            continue
        except (PermissionError, OSError):
            continue

    # Load baseline
    baseline = {}
    baseline_file = Path(baseline_path)
    if baseline_file.exists():
        try:
            baseline = json.loads(baseline_file.read_text())
        except Exception:
            pass

    # Compare
    changes = []
    new_files = []
    removed_files = []

    for path, checksum in current_checksums.items():
        if path not in baseline:
            new_files.append(path)
        elif baseline[path] != checksum:
            changes.append(path)

    for path in baseline:
        if path not in current_checksums:
            removed_files.append(path)

    # Save updated baseline
    try:
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        baseline_file.write_text(json.dumps(current_checksums, indent=2))
    except Exception as e:
        logger.error("[SystemScan] Failed to save baseline: %s", e)

    is_first_run = len(baseline) == 0

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files_scanned": len(current_checksums),
        "changes": changes,
        "new_files": new_files if not is_first_run else [],
        "removed_files": removed_files if not is_first_run else [],
        "is_first_run": is_first_run,
    }


def _hash_file(path: Path) -> str:
    """SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
