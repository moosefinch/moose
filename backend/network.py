"""
Network binding utilities — resolves the correct listen address.

Priority:
  1. MOOSE_BIND_HOST environment variable (explicit override)
  2. Tailscale interface IP (via `tailscale ip -4`)
  3. 127.0.0.1 fallback (Tailscale down or not installed)

The Tailscale IP is the only non-loopback address Moose should ever bind to.
Binding to 0.0.0.0 or a LAN IP is never acceptable in production.
"""

import logging
import os
import subprocess

logger = logging.getLogger(__name__)

# Tailscale CGNAT range: 100.64.0.0/10
_TS_RANGE_START = (100 << 24) | (64 << 16)   # 100.64.0.0
_TS_RANGE_END = (100 << 24) | (127 << 16) | (255 << 8) | 255  # 100.127.255.255

_FALLBACK = "127.0.0.1"


def _ip_to_int(ip: str) -> int:
    parts = ip.strip().split(".")
    if len(parts) != 4:
        return 0
    try:
        return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
    except ValueError:
        return 0


def is_tailscale_ip(ip: str) -> bool:
    """Return True if *ip* falls within the Tailscale CGNAT range (100.64/10)."""
    n = _ip_to_int(ip)
    return _TS_RANGE_START <= n <= _TS_RANGE_END


def get_tailscale_ip() -> str | None:
    """Query the Tailscale daemon for our IPv4 address. Returns None on failure."""
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=5,
        )
        ip = result.stdout.strip()
        if result.returncode == 0 and ip and is_tailscale_ip(ip):
            return ip
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_bind_host() -> str:
    """Determine the address Moose should bind to.

    Returns the Tailscale IP when available, 127.0.0.1 otherwise.
    MOOSE_BIND_HOST overrides everything.
    """
    override = os.environ.get("MOOSE_BIND_HOST", "").strip()
    if override:
        if override == "0.0.0.0":
            logger.warning("MOOSE_BIND_HOST=0.0.0.0 is insecure — refusing, using fallback")
        else:
            logger.info("Bind host override: %s", override)
            return override

    ts_ip = get_tailscale_ip()
    if ts_ip:
        logger.info("Binding to Tailscale interface: %s", ts_ip)
        return ts_ip

    logger.warning("Tailscale not available — falling back to %s", _FALLBACK)
    return _FALLBACK


def get_tailscale_subnet() -> str:
    """Return the Tailscale CGNAT /10 prefix for ACL checks."""
    return "100.64.0.0/10"


def is_allowed_source(ip: str) -> bool:
    """Return True if *ip* is localhost or within the Tailscale range."""
    if ip in ("127.0.0.1", "::1", "localhost"):
        return True
    return is_tailscale_ip(ip)
