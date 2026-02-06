#!/usr/bin/env python3
"""
Moose Security Validator — checks port bindings and network posture.

Run manually or at startup before accepting connections.
Zero external dependencies (stdlib only).

Usage:
    python3 security_check.py              # normal check
    python3 security_check.py --strict     # exit 1 on any WARNING
    python3 security_check.py --json       # machine-readable output

Exit codes:
    0 = all checks passed
    1 = one or more FAIL results (always fatal)
    2 = warnings present and --strict was used
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Expected secure state ──
# (service, port, allowed_binds, severity)
# allowed_binds: set of IPs that are acceptable.  "tailscale" is resolved
# at runtime.  "127.0.0.1" is always acceptable for localhost services.
POLICY = [
    ("Moose API",           8000,  {"tailscale", "127.0.0.1"},    "FAIL"),
    ("OpenClaw Gateway",    None,  {"127.0.0.1"},                 "FAIL"),
    ("CDP Debug",           9222,  {"127.0.0.1"},                 "FAIL"),
    ("Ollama",              11434, {"127.0.0.1"},                 "FAIL"),
    ("SearXNG",             8888,  {"127.0.0.1"},                 "WARN"),
    ("Herald Orchestrator", 8000,  {"127.0.0.1"},                 "WARN"),
    ("TTS Server",          8787,  {"127.0.0.1"},                 "WARN"),
    ("LM Studio",           1234,  {"127.0.0.1", "tailscale"},    "WARN"),
]

# ── Tailscale CGNAT ──
TS_START = (100 << 24) | (64 << 16)         # 100.64.0.0
TS_END   = (100 << 24) | (127 << 16) | 0xFFFF  # 100.127.255.255

LOG_DIR = Path.home() / "Library" / "Logs" / "moose"
LOG_FILE = LOG_DIR / "security_check.log"


def ip_to_int(ip: str) -> int:
    try:
        parts = ip.split(".")
        return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
    except (IndexError, ValueError):
        return 0


def is_tailscale(ip: str) -> bool:
    n = ip_to_int(ip)
    return TS_START <= n <= TS_END


def get_tailscale_ip() -> str | None:
    try:
        r = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5)
        ip = r.stdout.strip()
        if r.returncode == 0 and is_tailscale(ip):
            return ip
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_listeners() -> list[dict]:
    """Parse lsof output into a list of {pid, process, ip, port} dicts."""
    listeners = []
    try:
        r = subprocess.run(
            ["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
            capture_output=True, text=True, timeout=10,
        )
        for line in r.stdout.strip().splitlines()[1:]:  # skip header
            parts = line.split()
            if len(parts) < 9:
                continue
            proc = parts[0]
            pid = parts[1]
            name_col = parts[8]  # e.g. "127.0.0.1:8000" or "*:1234"

            m = re.match(r"^(.+):(\d+)$", name_col)
            if not m:
                continue
            ip_str = m.group(1)
            port = int(m.group(2))

            if ip_str == "*":
                ip_str = "0.0.0.0"

            listeners.append({
                "process": proc,
                "pid": pid,
                "ip": ip_str,
                "port": port,
            })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return listeners


def check_binding(listeners: list[dict], port: int, allowed: set[str], ts_ip: str | None) -> tuple[str, str]:
    """Check if a port is bound correctly.

    Returns (status, detail) where status is PASS/FAIL/WARN/SKIP.
    """
    bound = [l for l in listeners if l["port"] == port]
    if not bound:
        return "SKIP", "not listening"

    # Resolve "tailscale" placeholder
    resolved_allowed = set()
    for a in allowed:
        if a == "tailscale":
            if ts_ip:
                resolved_allowed.add(ts_ip)
        else:
            resolved_allowed.add(a)

    violations = []
    for entry in bound:
        ip = entry["ip"]
        if ip == "0.0.0.0":
            violations.append(f"{entry['process']}(pid={entry['pid']}) bound to 0.0.0.0:{port}")
        elif ip not in resolved_allowed and not is_tailscale(ip) if "tailscale" in allowed else ip not in resolved_allowed:
            violations.append(f"{entry['process']}(pid={entry['pid']}) bound to {ip}:{port}")

    if violations:
        return "VIOLATION", "; ".join(violations)

    procs = ", ".join(f"{e['process']}(pid={e['pid']}) on {e['ip']}" for e in bound)
    return "PASS", procs


def check_ollama_ipv6(listeners: list[dict]) -> tuple[str, str]:
    """Special check: Ollama IPv6 leak on *:11434."""
    # lsof shows IPv6 listeners as *:port too, but with IPv6 protocol
    try:
        r = subprocess.run(
            ["lsof", "-iTCP:11434", "-sTCP:LISTEN", "-P", "-n"],
            capture_output=True, text=True, timeout=10,
        )
        for line in r.stdout.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) < 5:
                continue
            # Column 4 is the file descriptor type (IPv4/IPv6)
            proto = parts[4]  # e.g., "IPv6"
            name_col = parts[8] if len(parts) > 8 else ""
            if proto == "IPv6" and name_col.startswith("*:"):
                return "VIOLATION", f"Ollama IPv6 on *:11434 — set OLLAMA_HOST=127.0.0.1:11434"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "PASS", "IPv6 not exposed"


def check_unexpected_listeners(listeners: list[dict], known_ports: set[int], ts_ip: str | None) -> list[dict]:
    """Flag any listener on 0.0.0.0 or LAN IPs that isn't in the known set."""
    flagged = []
    for l in listeners:
        if l["port"] in known_ports:
            continue
        ip = l["ip"]
        if ip == "0.0.0.0":
            flagged.append(l)
        elif ip not in ("127.0.0.1", "::1") and not is_tailscale(ip):
            flagged.append(l)
    return flagged


def run_checks(strict: bool = False, as_json: bool = False):
    ts_ip = get_tailscale_ip()
    listeners = get_listeners()
    results = []
    has_fail = False
    has_warn = False

    # Header
    hostname = socket.gethostname()
    now = datetime.now(timezone.utc).isoformat()

    if not as_json:
        print(f"Moose Security Check — {hostname} — {now}")
        print(f"Tailscale IP: {ts_ip or 'NOT AVAILABLE'}")
        print(f"{'—' * 60}")

    # ── Policy checks ──
    known_ports: set[int] = set()
    for service, port, allowed, severity in POLICY:
        if port is None:
            # OpenClaw Gateway: check any port bound by openclaw process
            oc = [l for l in listeners if "openclaw" in l["process"].lower()]
            if oc:
                for entry in oc:
                    if entry["ip"] not in ("127.0.0.1", "::1"):
                        status = "VIOLATION"
                        detail = f"{entry['process']} on {entry['ip']}:{entry['port']}"
                    else:
                        status = "PASS"
                        detail = f"{entry['ip']}:{entry['port']}"
                    results.append({"service": service, "port": entry["port"],
                                    "status": status, "detail": detail, "severity": severity})
            else:
                results.append({"service": service, "port": "N/A",
                                "status": "SKIP", "detail": "not running", "severity": severity})
            continue

        known_ports.add(port)
        status, detail = check_binding(listeners, port, allowed, ts_ip)
        if status == "VIOLATION":
            status = severity  # FAIL or WARN per policy
        results.append({"service": service, "port": port,
                        "status": status, "detail": detail, "severity": severity})

    # ── Ollama IPv6 special check ──
    ipv6_status, ipv6_detail = check_ollama_ipv6(listeners)
    if ipv6_status == "VIOLATION":
        results.append({"service": "Ollama IPv6", "port": 11434,
                        "status": "FAIL", "detail": ipv6_detail, "severity": "FAIL"})

    # ── Unexpected listeners ──
    # Add system ports we don't care about
    ignore_ports = {22, 5000, 7000, 49163, 49164, 7265, 49367, 41343, 59869}
    unexpected = check_unexpected_listeners(listeners, known_ports | ignore_ports, ts_ip)
    for u in unexpected:
        results.append({
            "service": f"UNKNOWN ({u['process']})",
            "port": u["port"],
            "status": "WARN",
            "detail": f"{u['process']}(pid={u['pid']}) on {u['ip']}:{u['port']}",
            "severity": "WARN",
        })

    # ── CDP specific check ──
    cdp_procs = [l for l in listeners if l["port"] == 9222]
    if cdp_procs:
        for p in cdp_procs:
            if p["ip"] != "127.0.0.1":
                results.append({
                    "service": "CDP Debug (CRITICAL)",
                    "port": 9222,
                    "status": "FAIL",
                    "detail": f"CDP on {p['ip']}:9222 — MUST be 127.0.0.1. "
                              "Set --remote-debugging-address=127.0.0.1",
                    "severity": "FAIL",
                })

    # ── Output ──
    if as_json:
        output = {
            "timestamp": now,
            "hostname": hostname,
            "tailscale_ip": ts_ip,
            "results": results,
        }
        print(json.dumps(output, indent=2))
    else:
        for r in results:
            tag = r["status"]
            icon = {"PASS": "+", "FAIL": "!", "WARN": "~", "SKIP": "-"}.get(tag, "?")
            print(f"  [{icon}] {tag:4s}  {r['service']:<22s}  :{str(r['port']):<6s}  {r['detail']}")
        print(f"{'—' * 60}")

    # ── Tally ──
    fails = [r for r in results if r["status"] == "FAIL"]
    warns = [r for r in results if r["status"] == "WARN"]
    passes = [r for r in results if r["status"] == "PASS"]
    skips = [r for r in results if r["status"] == "SKIP"]

    if not as_json:
        print(f"  {len(passes)} passed, {len(skips)} skipped, "
              f"{len(warns)} warnings, {len(fails)} failures")

    # ── Log to file ──
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{now}] {hostname}: "
                    f"{len(passes)}P {len(skips)}S {len(warns)}W {len(fails)}F")
            for r in results:
                if r["status"] in ("FAIL", "WARN"):
                    f.write(f"  | {r['status']} {r['service']} :{r['port']} {r['detail']}")
            f.write("\n")
    except OSError:
        pass

    # ── Exit code ──
    if fails:
        if not as_json:
            print("\n  FATAL: Security violations detected. Refusing to proceed.")
            for f in fails:
                print(f"    -> {f['service']} :{f['port']} — {f['detail']}")
        return 1

    if warns and strict:
        if not as_json:
            print("\n  STRICT MODE: Warnings treated as failures.")
        return 2

    if not as_json:
        print("\n  OK" if not warns else "\n  OK (with warnings)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Moose security validator")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as failures")
    parser.add_argument("--json", action="store_true",
                        help="JSON output")
    args = parser.parse_args()
    sys.exit(run_checks(strict=args.strict, as_json=args.json))
