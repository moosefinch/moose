#!/usr/bin/env python3
"""
General Prime Secure — Interactive Setup Wizard.

Generates profile.yaml and .gps_api_key for a fresh installation.
Run: python scripts/setup.py
"""

import json
import os
import secrets
import sys
from pathlib import Path

import httpx
import yaml

PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
PROFILE_PATH = PROJECT_ROOT / "profile.yaml"
API_KEY_PATH = BACKEND_DIR / ".gps_api_key"
PLIST_TEMPLATE = PROJECT_ROOT / "com.gps.backend.plist.template"
PLIST_OUTPUT = Path.home() / "Library" / "LaunchAgents" / "com.gps.backend.plist"


def _input(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    result = input(f"{prompt}{suffix}: ").strip()
    return result or default


def _yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    result = input(f"{prompt}{suffix}: ").strip().lower()
    if not result:
        return default
    return result in ("y", "yes")


def _probe_backend(endpoint: str) -> list[dict]:
    """Probe an inference backend for available models."""
    models = []
    try:
        resp = httpx.get(f"{endpoint}/v1/models", timeout=5)
        if resp.status_code == 200:
            for m in resp.json().get("data", []):
                models.append({"id": m.get("id", ""), "backend_type": "openai"})
            return models
    except Exception:
        pass

    # Try Ollama
    try:
        resp = httpx.get(f"{endpoint}/api/tags", timeout=5)
        if resp.status_code == 200:
            for m in resp.json().get("models", []):
                models.append({"id": m.get("name", ""), "backend_type": "ollama"})
            return models
    except Exception:
        pass

    return models


def _discover_backends() -> list[dict]:
    """Auto-detect LLM backends on common ports."""
    endpoints = [
        ("http://localhost:1234", "openai", "LM Studio / vLLM"),
        ("http://localhost:11434", "ollama", "Ollama"),
        ("http://localhost:8080", "llamacpp", "llama.cpp server"),
    ]
    found = []
    for endpoint, btype, label in endpoints:
        print(f"  Probing {endpoint} ({label})...", end=" ")
        models = _probe_backend(endpoint)
        if models:
            print(f"found {len(models)} model(s)")
            found.append({
                "name": btype,
                "type": btype if btype != "openai" else "openai",
                "endpoint": endpoint,
                "models": models,
            })
        else:
            print("not found")
    return found


def _select_model(models: list[dict], role: str) -> str:
    """Let user select a model for a given role."""
    if not models:
        return ""
    print(f"\n  Available models for {role}:")
    for i, m in enumerate(models):
        print(f"    [{i + 1}] {m['id']}")
    print(f"    [0] Skip (no {role} model)")
    while True:
        choice = input(f"  Select {role} model: ").strip()
        if choice == "0" or not choice:
            return ""
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                return models[idx]["id"]
        except ValueError:
            pass
        print("  Invalid choice, try again.")


def _generate_api_key() -> str:
    """Generate and save API key."""
    key = secrets.token_urlsafe(32)
    API_KEY_PATH.write_text(key)
    API_KEY_PATH.chmod(0o600)
    return key


def _generate_plist(install_dir: str, user_home: str, log_dir: str):
    """Generate launchd plist from template."""
    if not PLIST_TEMPLATE.exists():
        print("  Plist template not found, skipping.")
        return
    template = PLIST_TEMPLATE.read_text()
    plist = template.replace("{{INSTALL_DIR}}", install_dir)
    plist = plist.replace("{{USER_HOME}}", user_home)
    plist = plist.replace("{{LOG_DIR}}", log_dir)
    PLIST_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    PLIST_OUTPUT.write_text(plist)
    print(f"  Plist written to {PLIST_OUTPUT}")


def main():
    print("=" * 60)
    print("  General Prime Secure — Setup Wizard")
    print("=" * 60)
    print()

    # Step 1: System identity
    print("Step 1: System Identity")
    print("-" * 40)
    system_name = _input("System name", "Assistant")
    owner_name = _input("Owner name (your name)", "")
    organization = _input("Organization", "")
    print()

    # Step 2: Auto-detect backends
    print("Step 2: Discovering LLM Backends")
    print("-" * 40)
    backends = _discover_backends()

    all_models = []
    backend_configs = []
    if not backends:
        print("\n  No backends detected.")
        custom_endpoint = _input("  Enter a custom endpoint URL (or skip)", "")
        if custom_endpoint:
            models = _probe_backend(custom_endpoint)
            if models:
                backends = [{"name": "default", "type": "openai", "endpoint": custom_endpoint, "models": models}]
                all_models = models
                backend_configs = [{"name": "default", "type": "openai", "endpoint": custom_endpoint, "enabled": True}]
    else:
        for b in backends:
            all_models.extend(b["models"])
            backend_configs.append({
                "name": b["name"],
                "type": b["type"],
                "endpoint": b["endpoint"],
                "enabled": True,
            })
    print()

    # Step 3: Model assignment
    print("Step 3: Model Assignment")
    print("-" * 40)
    primary_model = _select_model(all_models, "primary (main reasoning)")
    classifier_model = _select_model(all_models, "classifier (fast routing)")
    security_model = _select_model(all_models, "security (monitoring)")
    embedder_model = _select_model(all_models, "embedder (vector memory)")
    print()

    # Step 4: Agent selection
    print("Step 4: Agent Selection")
    print("-" * 40)
    agents_config = {
        "classifier": {"enabled": True},  # Always enabled
    }
    agent_options = [
        ("hermes", "Deep reasoning engine"),
        ("security", "Security monitor"),
        ("coder", "Code specialist"),
        ("math", "Math/logic specialist"),
        ("reasoner", "Mission planner"),
        ("claude", "Claude API escalation"),
    ]
    for agent_id, desc in agent_options:
        enabled = _yes_no(f"  Enable {agent_id} ({desc})?", default=(agent_id in ("hermes", "reasoner", "coder")))
        agents_config[agent_id] = {"enabled": enabled}
    print()

    # Step 5: SMTP (optional)
    print("Step 5: SMTP Configuration (optional)")
    print("-" * 40)
    smtp_config = {"enabled": False}
    if _yes_no("  Configure SMTP for email sending?"):
        smtp_config = {
            "enabled": True,
            "host": _input("  SMTP host", ""),
            "port": int(_input("  SMTP port", "587")),
            "user": _input("  SMTP user", ""),
            "from_name": _input("  From name", system_name),
            "from_email": _input("  From email", ""),
            "use_tls": True,
            "sends_per_minute": 2,
        }
    print()

    # Step 6: Plugins
    print("Step 6: Plugins")
    print("-" * 40)
    crm_enabled = _yes_no("  Enable CRM plugin (outreach, campaigns, content)?")
    print()

    # Build profile
    profile = {
        "system": {
            "name": system_name,
            "description": "",
        },
        "owner": {
            "name": owner_name,
            "organization": organization,
            "focus_areas": [],
        },
        "company": {
            "name": organization,
            "domain": "",
            "value_proposition": "",
        },
        "web": {
            "cors_origins": [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            ],
        },
        "smtp": smtp_config,
        "inference": {
            "backends": backend_configs or [{"name": "default", "type": "openai", "endpoint": "http://localhost:1234", "enabled": True}],
            "models": {
                "primary": {"model_id": primary_model, "backend": "default", "vram_gb": 0, "max_tokens": 4096, "temperature": 0.7},
                "classifier": {"model_id": classifier_model, "backend": "default", "max_tokens": 10, "temperature": 0.1},
                "security": {"model_id": security_model, "backend": "default", "max_tokens": 4096, "temperature": 0.3},
                "embedder": {"model_id": embedder_model, "backend": "default"},
            },
        },
        "agents": agents_config,
        "plugins": {
            "crm": {"enabled": crm_enabled},
        },
        "prompts": {
            "personality": "",
            "domains": "",
        },
    }

    # Write profile.yaml
    print("=" * 60)
    print("  Writing configuration...")
    print("-" * 40)

    PROFILE_PATH.write_text(yaml.dump(profile, default_flow_style=False, sort_keys=False))
    print(f"  Profile written to {PROFILE_PATH}")

    # Generate API key
    if not API_KEY_PATH.exists():
        key = _generate_api_key()
        print(f"  API key generated: {key[:8]}...{key[-4:]}")
        print(f"  Saved to {API_KEY_PATH}")
    else:
        print(f"  API key already exists at {API_KEY_PATH}")

    # Generate plist
    if sys.platform == "darwin" and PLIST_TEMPLATE.exists():
        if _yes_no("\n  Generate launchd plist for daemon mode?"):
            _generate_plist(
                install_dir=str(PROJECT_ROOT),
                user_home=str(Path.home()),
                log_dir=str(Path.home() / "Library" / "Logs"),
            )

    print()
    print("=" * 60)
    print("  Setup complete!")
    print()
    print(f"  System name: {system_name}")
    print(f"  Owner: {owner_name or '(not set)'}")
    print(f"  Backends: {len(backend_configs)}")
    print(f"  Enabled agents: {[k for k, v in agents_config.items() if v.get('enabled')]}")
    print(f"  CRM plugin: {'enabled' if crm_enabled else 'disabled'}")
    print()
    print("  To start the server:")
    print("    cd backend && python main.py")
    print()
    print("  Or use the development start script:")
    print("    ./start.sh")
    print("=" * 60)


if __name__ == "__main__":
    main()
