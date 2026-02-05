"""
Profile System — loads profile.yaml and provides validated configuration.

The profile is the single source of truth for all user-configurable settings:
system name, owner, inference backends, model assignments, agent toggles,
SMTP, CORS origins, prompts, and plugin flags.

Usage:
    from profile import get_profile
    profile = get_profile()
    print(profile.system.name)
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# ── Profile Path Resolution ──
_PROFILE_PATH_ENV = os.environ.get("PROFILE_PATH")
_PROJECT_ROOT = Path(__file__).parent.parent
_DEFAULT_PROFILE_PATH = _PROJECT_ROOT / "profile.yaml"


# ── Dataclasses ──

@dataclass
class SystemConfig:
    name: str = "Assistant"
    description: str = ""


@dataclass
class OwnerConfig:
    name: str = ""
    organization: str = ""
    focus_areas: list[str] = field(default_factory=list)


@dataclass
class CompanyConfig:
    name: str = ""
    domain: str = ""
    value_proposition: str = ""


@dataclass
class WebConfig:
    cors_origins: list[str] = field(default_factory=lambda: [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ])


@dataclass
class SmtpConfig:
    enabled: bool = False
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""  # loaded from env or .secrets
    from_name: str = ""
    from_email: str = ""
    use_tls: bool = True
    sends_per_minute: float = 2.0


@dataclass
class InferenceBackendConfig:
    name: str = "default"
    type: str = "openai"  # openai | ollama | llamacpp
    endpoint: str = "http://localhost:1234"
    enabled: bool = True


@dataclass
class ModelConfig:
    model_id: str = ""
    backend: str = "default"
    vram_gb: float = 0.0
    max_tokens: int = 4096
    temperature: float = 0.7
    tier: str = "on_demand"  # "always_loaded" or "on_demand"


@dataclass
class ModelsConfig:
    primary: ModelConfig = field(default_factory=ModelConfig)
    conversational: ModelConfig = field(default_factory=lambda: ModelConfig(
        max_tokens=2048, temperature=0.7, tier="always_loaded"))
    orchestrator: ModelConfig = field(default_factory=lambda: ModelConfig(
        max_tokens=1024, temperature=0.3, tier="always_loaded"))
    classifier: ModelConfig = field(default_factory=lambda: ModelConfig(
        max_tokens=10, temperature=0.1, tier="always_loaded"))
    security: ModelConfig = field(default_factory=lambda: ModelConfig(
        max_tokens=4096, temperature=0.3))
    embedder: ModelConfig = field(default_factory=lambda: ModelConfig(
        max_tokens=0, temperature=0.0, tier="always_loaded"))


@dataclass
class InferenceConfig:
    backends: list[InferenceBackendConfig] = field(default_factory=lambda: [InferenceBackendConfig()])
    models: ModelsConfig = field(default_factory=ModelsConfig)


@dataclass
class AgentToggle:
    enabled: bool = False


@dataclass
class AgentsConfig:
    hermes: AgentToggle = field(default_factory=AgentToggle)
    classifier: AgentToggle = field(default_factory=lambda: AgentToggle(enabled=True))
    security: AgentToggle = field(default_factory=AgentToggle)
    coder: AgentToggle = field(default_factory=AgentToggle)
    math: AgentToggle = field(default_factory=AgentToggle)
    reasoner: AgentToggle = field(default_factory=AgentToggle)
    claude: AgentToggle = field(default_factory=AgentToggle)


@dataclass
class PluginToggle:
    enabled: bool = False


@dataclass
class TelegramPluginConfig:
    enabled: bool = False
    token: str = ""  # loaded from MOOSE_TELEGRAM_TOKEN env var


@dataclass
class SlackPluginConfig:
    enabled: bool = False
    bot_token: str = ""   # loaded from MOOSE_SLACK_BOT_TOKEN env var
    app_token: str = ""   # loaded from MOOSE_SLACK_APP_TOKEN env var


@dataclass
class BlenderPluginConfig:
    enabled: bool = False
    blender_path: str = ""  # Override for Blender executable path


@dataclass
class PrintingPluginConfig:
    enabled: bool = False
    printer_ip: str = ""
    access_code: str = ""  # Bambu Lab printer access code
    serial: str = ""       # Printer serial number (for MQTT topic)
    ftps_port: int = 990


@dataclass
class PluginsConfig:
    crm: PluginToggle = field(default_factory=PluginToggle)
    telegram: TelegramPluginConfig = field(default_factory=TelegramPluginConfig)
    slack: SlackPluginConfig = field(default_factory=SlackPluginConfig)
    blender: BlenderPluginConfig = field(default_factory=BlenderPluginConfig)
    printing: PrintingPluginConfig = field(default_factory=PrintingPluginConfig)


@dataclass
class PromptsConfig:
    personality: str = ""
    domains: str = ""


@dataclass
class CognitiveLoopConfig:
    enabled: bool = False
    cycle_interval_seconds: int = 120
    min_interval_seconds: int = 30
    reflection_every_n_cycles: int = 10
    morning_briefing_hour: int = 9
    evening_briefing_hour: int = 18


@dataclass
class AdvocacyUserConfig:
    name: str = ""
    age: Optional[int] = None
    context: str = ""


@dataclass
class AdvocateConfig:
    name: str = ""
    relationship: str = ""  # partner, parent, therapist, coach, friend
    channel: str = ""  # email, slack, telegram
    categories: list[str] = field(default_factory=list)
    escalation_threshold: int = 3  # minimum friction level
    can_set_boundaries: bool = False
    visibility: str = "themes"  # themes | full | none


@dataclass
class DevelopmentalConfig:
    mode: str = "adult"  # child | adolescent | adult


@dataclass
class AdvocacyConfig:
    enabled: bool = False
    profile: str = "solo"  # solo | partnered | guided | custom
    user: AdvocacyUserConfig = field(default_factory=AdvocacyUserConfig)
    goals_cap: int = 50
    patterns_cap: int = 100
    cooloff_days: int = 14
    max_flags_per_day: int = 3
    advocates: list[AdvocateConfig] = field(default_factory=list)
    developmental: DevelopmentalConfig = field(default_factory=DevelopmentalConfig)


@dataclass
class Profile:
    system: SystemConfig = field(default_factory=SystemConfig)
    owner: OwnerConfig = field(default_factory=OwnerConfig)
    company: CompanyConfig = field(default_factory=CompanyConfig)
    web: WebConfig = field(default_factory=WebConfig)
    smtp: SmtpConfig = field(default_factory=SmtpConfig)
    inference: InferenceConfig = field(default_factory=InferenceConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
    prompts: PromptsConfig = field(default_factory=PromptsConfig)
    cognitive_loop: CognitiveLoopConfig = field(default_factory=CognitiveLoopConfig)
    advocacy: AdvocacyConfig = field(default_factory=AdvocacyConfig)

    def is_agent_enabled(self, agent_id: str) -> bool:
        """Check if an agent is enabled in the profile."""
        toggle = getattr(self.agents, agent_id, None)
        if toggle is None:
            return False
        return toggle.enabled

    def get_enabled_agents(self) -> list[str]:
        """Return list of enabled agent IDs."""
        return [
            aid for aid in ("hermes", "classifier", "security", "coder",
                            "math", "reasoner", "claude")
            if self.is_agent_enabled(aid)
        ]

    def get_backend(self, name: str = "default") -> Optional[InferenceBackendConfig]:
        """Get an inference backend config by name."""
        for b in self.inference.backends:
            if b.name == name:
                return b
        return None

    def get_default_endpoint(self) -> str:
        """Get the endpoint URL for the default backend."""
        backend = self.get_backend("default")
        return backend.endpoint if backend else "http://localhost:1234"


# ── Parsing ──

def _parse_dict(data: dict, cls, **overrides):
    """Create a dataclass instance from a dict, ignoring unknown keys."""
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in data.items() if k in field_names}
    filtered.update(overrides)
    return cls(**filtered)


def _load_profile_from_dict(raw: dict) -> Profile:
    """Parse a raw YAML dict into a Profile dataclass."""
    profile = Profile()

    # System
    if "system" in raw and isinstance(raw["system"], dict):
        profile.system = _parse_dict(raw["system"], SystemConfig)

    # Owner
    if "owner" in raw and isinstance(raw["owner"], dict):
        profile.owner = _parse_dict(raw["owner"], OwnerConfig)

    # Company
    if "company" in raw and isinstance(raw["company"], dict):
        profile.company = _parse_dict(raw["company"], CompanyConfig)

    # Web
    if "web" in raw and isinstance(raw["web"], dict):
        profile.web = _parse_dict(raw["web"], WebConfig)

    # SMTP
    if "smtp" in raw and isinstance(raw["smtp"], dict):
        smtp_data = raw["smtp"].copy()
        # Load password from env var
        smtp_data.setdefault("password",
                             os.environ.get("MOOSE_SMTP_PASSWORD", ""))
        profile.smtp = _parse_dict(smtp_data, SmtpConfig)

    # Inference
    if "inference" in raw and isinstance(raw["inference"], dict):
        inf_raw = raw["inference"]
        backends = []
        for b in inf_raw.get("backends", []):
            if isinstance(b, dict):
                backends.append(_parse_dict(b, InferenceBackendConfig))
        if not backends:
            backends = [InferenceBackendConfig()]

        models = ModelsConfig()
        models_raw = inf_raw.get("models", {})
        if isinstance(models_raw, dict):
            if "primary" in models_raw and isinstance(models_raw["primary"], dict):
                models.primary = _parse_dict(models_raw["primary"], ModelConfig)
            if "conversational" in models_raw and isinstance(models_raw["conversational"], dict):
                models.conversational = _parse_dict(models_raw["conversational"], ModelConfig,
                                                     tier=models_raw["conversational"].get("tier", "always_loaded"))
            if "orchestrator" in models_raw and isinstance(models_raw["orchestrator"], dict):
                models.orchestrator = _parse_dict(models_raw["orchestrator"], ModelConfig,
                                                    tier=models_raw["orchestrator"].get("tier", "always_loaded"))
            if "classifier" in models_raw and isinstance(models_raw["classifier"], dict):
                models.classifier = _parse_dict(models_raw["classifier"], ModelConfig,
                                                 max_tokens=models_raw["classifier"].get("max_tokens", 10),
                                                 temperature=models_raw["classifier"].get("temperature", 0.1),
                                                 tier=models_raw["classifier"].get("tier", "always_loaded"))
            if "security" in models_raw and isinstance(models_raw["security"], dict):
                models.security = _parse_dict(models_raw["security"], ModelConfig,
                                               max_tokens=models_raw["security"].get("max_tokens", 4096),
                                               temperature=models_raw["security"].get("temperature", 0.3))
            if "embedder" in models_raw and isinstance(models_raw["embedder"], dict):
                models.embedder = _parse_dict(models_raw["embedder"], ModelConfig,
                                               tier=models_raw["embedder"].get("tier", "always_loaded"))

        profile.inference = InferenceConfig(backends=backends, models=models)

    # Agents
    if "agents" in raw and isinstance(raw["agents"], dict):
        agents = AgentsConfig()
        for agent_id in ("hermes", "classifier", "security", "coder", "math", "reasoner", "claude"):
            agent_raw = raw["agents"].get(agent_id, {})
            if isinstance(agent_raw, dict):
                enabled = agent_raw.get("enabled", False)
                setattr(agents, agent_id, AgentToggle(enabled=enabled))
        profile.agents = agents

    # Plugins
    if "plugins" in raw and isinstance(raw["plugins"], dict):
        plugins = PluginsConfig()
        for plugin_id in ("crm",):
            plugin_raw = raw["plugins"].get(plugin_id, {})
            if isinstance(plugin_raw, dict):
                enabled = plugin_raw.get("enabled", False)
                setattr(plugins, plugin_id, PluginToggle(enabled=enabled))

        # Telegram plugin
        tg_raw = raw["plugins"].get("telegram", {})
        if isinstance(tg_raw, dict):
            plugins.telegram = TelegramPluginConfig(
                enabled=tg_raw.get("enabled", False),
                token=os.environ.get("MOOSE_TELEGRAM_TOKEN", tg_raw.get("token", "")),
            )

        # Slack plugin
        sl_raw = raw["plugins"].get("slack", {})
        if isinstance(sl_raw, dict):
            plugins.slack = SlackPluginConfig(
                enabled=sl_raw.get("enabled", False),
                bot_token=os.environ.get("MOOSE_SLACK_BOT_TOKEN", sl_raw.get("bot_token", "")),
                app_token=os.environ.get("MOOSE_SLACK_APP_TOKEN", sl_raw.get("app_token", "")),
            )

        # Blender plugin
        bl_raw = raw["plugins"].get("blender", {})
        if isinstance(bl_raw, dict):
            plugins.blender = BlenderPluginConfig(
                enabled=bl_raw.get("enabled", False),
                blender_path=bl_raw.get("blender_path", ""),
            )

        # Printing plugin (Bambu Labs)
        pr_raw = raw["plugins"].get("printing", {})
        if isinstance(pr_raw, dict):
            plugins.printing = PrintingPluginConfig(
                enabled=pr_raw.get("enabled", False),
                printer_ip=pr_raw.get("printer_ip", ""),
                access_code=os.environ.get("MOOSE_PRINTER_ACCESS_CODE",
                                           pr_raw.get("access_code", "")),
                serial=pr_raw.get("serial", ""),
                ftps_port=pr_raw.get("ftps_port", 990),
            )

        profile.plugins = plugins

    # Prompts
    if "prompts" in raw and isinstance(raw["prompts"], dict):
        profile.prompts = _parse_dict(raw["prompts"], PromptsConfig)

    # Cognitive Loop
    if "cognitive_loop" in raw and isinstance(raw["cognitive_loop"], dict):
        profile.cognitive_loop = _parse_dict(raw["cognitive_loop"], CognitiveLoopConfig)

    # Advocacy
    if "advocacy" in raw and isinstance(raw["advocacy"], dict):
        adv_raw = raw["advocacy"]
        advocacy = AdvocacyConfig(
            enabled=adv_raw.get("enabled", False),
            profile=adv_raw.get("profile", "solo"),
            goals_cap=adv_raw.get("goals_cap", 50),
            patterns_cap=adv_raw.get("patterns_cap", 100),
            cooloff_days=adv_raw.get("cooloff_days", 14),
            max_flags_per_day=adv_raw.get("max_flags_per_day", 3),
        )

        # User config
        user_raw = adv_raw.get("user", {})
        if isinstance(user_raw, dict):
            advocacy.user = AdvocacyUserConfig(
                name=user_raw.get("name", ""),
                age=user_raw.get("age"),
                context=user_raw.get("context", ""),
            )

        # Developmental config
        dev_raw = adv_raw.get("developmental", {})
        if isinstance(dev_raw, dict):
            advocacy.developmental = DevelopmentalConfig(
                mode=dev_raw.get("mode", "adult"),
            )

        # Advocates list
        advocates_raw = adv_raw.get("advocates", [])
        if isinstance(advocates_raw, list):
            for a in advocates_raw:
                if isinstance(a, dict):
                    advocacy.advocates.append(AdvocateConfig(
                        name=a.get("name", ""),
                        relationship=a.get("relationship", ""),
                        channel=a.get("channel", ""),
                        categories=a.get("categories", []),
                        escalation_threshold=a.get("escalation_threshold", 3),
                        can_set_boundaries=a.get("can_set_boundaries", False),
                        visibility=a.get("visibility", "themes"),
                    ))

        profile.advocacy = advocacy

    return profile


def _load_profile() -> Profile:
    """Load profile from YAML file. Falls back to defaults if missing."""
    profile_path = Path(_PROFILE_PATH_ENV) if _PROFILE_PATH_ENV else _DEFAULT_PROFILE_PATH

    if not profile_path.exists():
        logger.info("No profile.yaml found at %s — using defaults", profile_path)
        return Profile()

    try:
        raw = yaml.safe_load(profile_path.read_text()) or {}
        if not isinstance(raw, dict):
            logger.warning("profile.yaml is not a valid YAML mapping — using defaults")
            return Profile()
        profile = _load_profile_from_dict(raw)
        logger.info("Profile loaded: system=%s, owner=%s, agents=%s",
                     profile.system.name, profile.owner.name or "(none)",
                     profile.get_enabled_agents())
        return profile
    except Exception as e:
        logger.error("Failed to load profile.yaml: %s — using defaults", e)
        return Profile()


# ── Singleton ──

_profile: Optional[Profile] = None


def get_profile() -> Profile:
    """Return the validated profile singleton. Loads on first call."""
    global _profile
    if _profile is None:
        _profile = _load_profile()
    return _profile


def reload_profile() -> Profile:
    """Force reload of the profile from disk."""
    global _profile
    _profile = _load_profile()
    return _profile
