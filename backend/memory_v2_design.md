# Moose Memory V2 — Self-Aware Tiered Memory System

## Overview

A memory architecture for a personal AI that:
1. **Knows itself** — detects hardware, monitors resources, adapts to constraints
2. **Learns the user** — builds understanding through interaction, not configuration
3. **Compounds over time** — more interactions = better understanding, not slower queries
4. **Runs anywhere** — from a Raspberry Pi to a workstation, adapts automatically

---

## Part 1: System Self-Awareness

Moose must understand the environment it's running in.

### System Profile (Auto-Detected)

```sql
-- System hardware and capabilities (auto-populated on startup)
CREATE TABLE system_profile (
    id INTEGER PRIMARY KEY DEFAULT 1,

    -- Hardware (detected via psutil, platform, etc.)
    hostname TEXT,
    os_type TEXT,                       -- "darwin", "linux", "windows"
    os_version TEXT,
    cpu_model TEXT,
    cpu_cores INTEGER,
    cpu_threads INTEGER,
    ram_total_gb REAL,
    gpu_model TEXT,                     -- NULL if no GPU
    gpu_vram_gb REAL,
    disk_total_gb REAL,

    -- Detected capabilities
    has_gpu INTEGER DEFAULT 0,
    has_neural_engine INTEGER DEFAULT 0,  -- Apple Silicon
    has_cuda INTEGER DEFAULT 0,
    has_rocm INTEGER DEFAULT 0,           -- AMD
    has_metal INTEGER DEFAULT 0,          -- macOS

    -- Derived constraints
    max_model_size_gb REAL,             -- Largest model that fits in memory
    recommended_context_tokens INTEGER, -- Based on available RAM
    can_run_embeddings_locally INTEGER DEFAULT 1,

    -- Last updated
    detected_at REAL DEFAULT (unixepoch()),
    updated_at REAL DEFAULT (unixepoch())
);

-- Real-time resource snapshots (updated periodically)
CREATE TABLE resource_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL DEFAULT (unixepoch()),

    -- Memory
    ram_used_gb REAL,
    ram_available_gb REAL,
    ram_percent REAL,

    -- CPU
    cpu_percent REAL,
    load_avg_1m REAL,
    load_avg_5m REAL,

    -- GPU (if available)
    gpu_used_gb REAL,
    gpu_available_gb REAL,
    gpu_percent REAL,

    -- Disk
    disk_used_gb REAL,
    disk_available_gb REAL,

    -- Inference backend
    lm_studio_loaded_models TEXT,       -- JSON array
    lm_studio_vram_used_gb REAL,

    -- Moose-specific
    memory_entry_count INTEGER,
    active_sessions INTEGER,
    pending_extractions INTEGER
);

CREATE INDEX idx_resource_snapshots_time ON resource_snapshots(timestamp DESC);

-- Process inventory (what's running on this machine)
CREATE TABLE process_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pid INTEGER,
    name TEXT,
    cmdline TEXT,
    cpu_percent REAL,
    memory_mb REAL,
    category TEXT,                      -- "inference", "ide", "browser", "system", "user_app"
    first_seen REAL DEFAULT (unixepoch()),
    last_seen REAL DEFAULT (unixepoch())
);

CREATE INDEX idx_process_inventory_name ON process_inventory(name);
CREATE INDEX idx_process_inventory_category ON process_inventory(category);
```

### System Detection Logic

```python
# backend/memory_v2/system_awareness.py

import platform
import psutil
import subprocess
import json
from pathlib import Path

class SystemAwareness:
    """Detect and monitor the system Moose is running on."""

    def __init__(self, db):
        self.db = db
        self._profile = None

    def detect_hardware(self) -> dict:
        """Detect hardware capabilities. Run once on startup."""
        profile = {
            "hostname": platform.node(),
            "os_type": platform.system().lower(),
            "os_version": platform.release(),
            "cpu_model": self._get_cpu_model(),
            "cpu_cores": psutil.cpu_count(logical=False),
            "cpu_threads": psutil.cpu_count(logical=True),
            "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            "disk_total_gb": round(psutil.disk_usage('/').total / (1024**3), 1),
        }

        # GPU detection
        gpu_info = self._detect_gpu()
        profile.update(gpu_info)

        # Capability flags
        profile["has_gpu"] = gpu_info.get("gpu_model") is not None
        profile["has_neural_engine"] = self._has_neural_engine()
        profile["has_cuda"] = self._has_cuda()
        profile["has_rocm"] = self._has_rocm()
        profile["has_metal"] = profile["os_type"] == "darwin"

        # Derive constraints
        profile["max_model_size_gb"] = self._calculate_max_model_size(profile)
        profile["recommended_context_tokens"] = self._calculate_context_budget(profile)
        profile["can_run_embeddings_locally"] = profile["ram_total_gb"] >= 8

        # Store in database
        self.db.upsert("system_profile", profile, conflict_keys=["id"])
        self._profile = profile

        return profile

    def _get_cpu_model(self) -> str:
        """Get CPU model string."""
        if platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True, text=True
                )
                return result.stdout.strip()
            except:
                pass

        if platform.system() == "Linux":
            try:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line:
                            return line.split(":")[1].strip()
            except:
                pass

        return platform.processor() or "Unknown"

    def _detect_gpu(self) -> dict:
        """Detect GPU model and VRAM."""
        result = {"gpu_model": None, "gpu_vram_gb": None}

        # macOS - check for Apple Silicon GPU
        if platform.system() == "Darwin":
            try:
                sp = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType", "-json"],
                    capture_output=True, text=True
                )
                data = json.loads(sp.stdout)
                displays = data.get("SPDisplaysDataType", [])
                if displays:
                    gpu = displays[0]
                    result["gpu_model"] = gpu.get("sppci_model", "Apple GPU")
                    # Apple Silicon shares unified memory
                    result["gpu_vram_gb"] = None  # Shared with RAM
            except:
                pass

        # NVIDIA GPU
        try:
            nvidia = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True
            )
            if nvidia.returncode == 0:
                parts = nvidia.stdout.strip().split(", ")
                result["gpu_model"] = parts[0]
                if len(parts) > 1:
                    vram = parts[1].replace("MiB", "").strip()
                    result["gpu_vram_gb"] = round(int(vram) / 1024, 1)
        except:
            pass

        return result

    def _has_neural_engine(self) -> bool:
        """Check for Apple Neural Engine."""
        if platform.system() != "Darwin":
            return False
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.optional.arm64"],
                capture_output=True, text=True
            )
            return result.stdout.strip() == "1"
        except:
            return False

    def _has_cuda(self) -> bool:
        """Check for CUDA support."""
        try:
            result = subprocess.run(["nvidia-smi"], capture_output=True)
            return result.returncode == 0
        except:
            return False

    def _has_rocm(self) -> bool:
        """Check for AMD ROCm support."""
        try:
            result = subprocess.run(["rocm-smi"], capture_output=True)
            return result.returncode == 0
        except:
            return False

    def _calculate_max_model_size(self, profile: dict) -> float:
        """Calculate largest model that can reasonably run."""
        ram = profile["ram_total_gb"]
        vram = profile.get("gpu_vram_gb") or 0

        # Apple Silicon uses unified memory
        if profile.get("has_metal") and profile.get("has_neural_engine"):
            # Can use most of RAM for model, leave ~8GB for system
            return max(0, ram - 8)

        # Discrete GPU - limited by VRAM
        if vram > 0:
            return vram * 0.9  # Leave 10% headroom

        # CPU-only inference
        return max(0, (ram - 8) * 0.6)  # Conservative for CPU inference

    def _calculate_context_budget(self, profile: dict) -> int:
        """Calculate recommended context window based on resources."""
        ram = profile["ram_total_gb"]

        # More RAM = larger context budget
        if ram >= 128:
            return 32000
        elif ram >= 64:
            return 24000
        elif ram >= 32:
            return 16000
        elif ram >= 16:
            return 8000
        else:
            return 4000

    def snapshot_resources(self) -> dict:
        """Take a snapshot of current resource usage."""
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        snapshot = {
            "ram_used_gb": round((mem.total - mem.available) / (1024**3), 2),
            "ram_available_gb": round(mem.available / (1024**3), 2),
            "ram_percent": mem.percent,
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "load_avg_1m": psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0,
            "load_avg_5m": psutil.getloadavg()[1] if hasattr(psutil, 'getloadavg') else 0,
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_available_gb": round(disk.free / (1024**3), 2),
        }

        # GPU usage (if NVIDIA)
        try:
            nvidia = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if nvidia.returncode == 0:
                parts = nvidia.stdout.strip().split(", ")
                snapshot["gpu_used_gb"] = round(int(parts[0]) / 1024, 2)
                snapshot["gpu_available_gb"] = round(int(parts[1]) / 1024, 2)
                snapshot["gpu_percent"] = float(parts[2])
        except:
            pass

        # LM Studio loaded models (if running)
        snapshot["lm_studio_loaded_models"] = json.dumps(
            self._get_lm_studio_models()
        )

        # Moose internal stats
        snapshot["memory_entry_count"] = self.db.query_one(
            "SELECT COUNT(*) as c FROM memories"
        ).c if self.db.table_exists("memories") else 0

        # Store snapshot
        self.db.insert("resource_snapshots", snapshot)

        # Prune old snapshots (keep last 24 hours)
        self.db.execute("""
            DELETE FROM resource_snapshots
            WHERE timestamp < unixepoch() - 86400
        """)

        return snapshot

    def _get_lm_studio_models(self) -> list:
        """Get currently loaded models from LM Studio."""
        try:
            import httpx
            resp = httpx.get("http://localhost:1234/v1/models", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
        except:
            pass
        return []

    def inventory_processes(self):
        """Inventory running processes and categorize them."""
        categories = {
            "lm-studio": "inference",
            "ollama": "inference",
            "llama": "inference",
            "python": "user_app",
            "node": "user_app",
            "code": "ide",
            "cursor": "ide",
            "vim": "ide",
            "nvim": "ide",
            "chrome": "browser",
            "firefox": "browser",
            "safari": "browser",
        }

        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info']):
            try:
                info = proc.info
                name = (info['name'] or '').lower()

                # Categorize
                category = "system"
                for pattern, cat in categories.items():
                    if pattern in name:
                        category = cat
                        break

                self.db.upsert("process_inventory", {
                    "pid": info['pid'],
                    "name": info['name'],
                    "cmdline": ' '.join(info['cmdline'] or [])[:500],
                    "cpu_percent": info['cpu_percent'] or 0,
                    "memory_mb": (info['memory_info'].rss / (1024**2)) if info['memory_info'] else 0,
                    "category": category,
                    "last_seen": "unixepoch()",
                }, conflict_keys=["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def get_profile(self) -> dict:
        """Get cached system profile."""
        if not self._profile:
            self._profile = self.db.query_one("SELECT * FROM system_profile WHERE id = 1")
        return self._profile

    def get_adaptive_context_budget(self) -> dict:
        """Get context budget adapted to current resource availability."""
        profile = self.get_profile()
        base_budget = profile.get("recommended_context_tokens", 8000)

        # Get latest resource snapshot
        snapshot = self.db.query_one("""
            SELECT * FROM resource_snapshots ORDER BY timestamp DESC LIMIT 1
        """)

        if not snapshot:
            return {"core": 500, "session": 2000, "retrieved": base_budget - 2500}

        # Adjust based on current availability
        ram_pressure = snapshot.get("ram_percent", 50) / 100

        if ram_pressure > 0.9:
            # System under heavy load - minimize context
            multiplier = 0.5
        elif ram_pressure > 0.7:
            # Moderate load - reduce context
            multiplier = 0.75
        else:
            # Normal - full budget
            multiplier = 1.0

        adjusted_budget = int(base_budget * multiplier)

        return {
            "total": adjusted_budget,
            "core": 500,  # Core identity is always small
            "session": min(4000, int(adjusted_budget * 0.3)),
            "retrieved": adjusted_budget - 500 - min(4000, int(adjusted_budget * 0.3)),
            "multiplier": multiplier,
            "reason": f"RAM at {snapshot.get('ram_percent', 0):.0f}%"
        }
```

---

## Part 2: User Model (Self-Populating)

The user model builds itself through interaction — no configuration required.

### Schema

```sql
-- User identity (learned, not configured)
CREATE TABLE user_identity (
    id INTEGER PRIMARY KEY DEFAULT 1,

    -- Basics (may start NULL, learned over time)
    name TEXT,
    preferred_name TEXT,                -- How they like to be addressed
    timezone TEXT,
    locale TEXT,

    -- Inferred attributes
    role TEXT,                          -- "engineer", "designer", "student", etc.
    experience_level TEXT,              -- "beginner", "intermediate", "advanced", "expert"
    primary_domain TEXT,                -- "robotics", "web", "ml", "embedded", etc.

    -- Communication style (observed)
    verbosity_preference TEXT,          -- "concise", "detailed", "balanced"
    formality_level TEXT,               -- "casual", "professional", "mixed"

    -- Confidence in identity
    identity_confidence REAL DEFAULT 0.0,  -- Grows as we learn more

    created_at REAL DEFAULT (unixepoch()),
    updated_at REAL DEFAULT (unixepoch())
);

-- User preferences (accumulated through interaction)
CREATE TABLE user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Categorization
    domain TEXT NOT NULL,               -- "code", "communication", "workflow", "tools", etc.
    scope TEXT DEFAULT 'global',        -- "global", project_id, or specific context

    -- The preference
    key TEXT NOT NULL,                  -- "naming_convention", "indentation", "editor"
    value TEXT NOT NULL,                -- The actual preference

    -- How we know this
    source TEXT DEFAULT 'inferred',     -- "explicit" (user told us), "inferred", "observed"
    evidence TEXT,                      -- What led to this inference
    evidence_count INTEGER DEFAULT 1,   -- How many times we've seen this

    -- Confidence and validity
    confidence REAL DEFAULT 0.5,
    first_observed REAL DEFAULT (unixepoch()),
    last_confirmed REAL DEFAULT (unixepoch()),

    -- For conflict resolution
    contradicted_by INTEGER REFERENCES user_preferences(id),
    active INTEGER DEFAULT 1
);

CREATE INDEX idx_user_prefs_domain ON user_preferences(domain);
CREATE INDEX idx_user_prefs_key ON user_preferences(key);
CREATE INDEX idx_user_prefs_active ON user_preferences(active) WHERE active = 1;
CREATE UNIQUE INDEX idx_user_prefs_unique ON user_preferences(domain, scope, key) WHERE active = 1;

-- Projects (discovered and tracked)
CREATE TABLE projects (
    id TEXT PRIMARY KEY,                -- Derived from path or name

    -- Basic info
    name TEXT NOT NULL,
    description TEXT,

    -- Location
    path TEXT,                          -- Local filesystem path
    repo_url TEXT,                      -- Git remote if available

    -- Classification
    domain TEXT,                        -- "robotics", "web", "ml", etc.
    project_type TEXT,                  -- "application", "library", "firmware", etc.

    -- Tech stack (auto-detected)
    languages TEXT,                     -- JSON array: ["python", "c++"]
    frameworks TEXT,                    -- JSON array: ["ros2", "react"]
    build_system TEXT,                  -- "cmake", "cargo", "npm", etc.

    -- Status
    status TEXT DEFAULT 'active',       -- "active", "paused", "completed", "archived"
    priority INTEGER DEFAULT 0,

    -- Activity tracking
    first_seen REAL DEFAULT (unixepoch()),
    last_active REAL DEFAULT (unixepoch()),
    interaction_count INTEGER DEFAULT 0,

    -- Detection metadata
    auto_detected INTEGER DEFAULT 0,    -- 1 if we found this ourselves
    detection_source TEXT               -- "cwd", "git", "mentioned", "file_access"
);

CREATE INDEX idx_projects_status ON projects(status);
CREATE INDEX idx_projects_last_active ON projects(last_active DESC);
CREATE INDEX idx_projects_path ON projects(path);

-- Project-specific knowledge
CREATE TABLE project_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- What kind of knowledge
    knowledge_type TEXT NOT NULL,       -- "architecture", "convention", "decision", "issue", "solution"

    -- The knowledge
    content TEXT NOT NULL,

    -- Metadata
    file_path TEXT,                     -- If this relates to a specific file
    importance REAL DEFAULT 0.5,

    -- Temporal
    created_at REAL DEFAULT (unixepoch()),
    valid_to REAL,                      -- NULL = still valid
    superseded_by INTEGER REFERENCES project_knowledge(id),

    -- Access tracking
    last_accessed REAL,
    access_count INTEGER DEFAULT 0
);

CREATE INDEX idx_project_knowledge_project ON project_knowledge(project_id);
CREATE INDEX idx_project_knowledge_type ON project_knowledge(knowledge_type);
```

### Self-Population Logic

```python
# backend/memory_v2/user_model.py

class UserModel:
    """Self-populating user model that learns through interaction."""

    def __init__(self, db, llm_client):
        self.db = db
        self.llm = llm_client

    async def learn_from_interaction(self, user_msg: str, assistant_msg: str,
                                     context: dict = None):
        """Extract learnings from an interaction."""

        # 1. Identity signals
        await self._update_identity_from_interaction(user_msg, assistant_msg)

        # 2. Preference signals
        await self._extract_preferences(user_msg, assistant_msg)

        # 3. Project signals
        await self._detect_project_context(user_msg, context)

    async def _update_identity_from_interaction(self, user_msg: str, assistant_msg: str):
        """Update identity based on interaction signals."""

        # Check for explicit identity statements
        identity_patterns = {
            r"my name is (\w+)": "name",
            r"i'm (\w+)": "preferred_name",  # Could be name or role
            r"i work as (?:a |an )?(.+?)(?:\.|,|$)": "role",
            r"i'm (?:a |an )?(.+?) (?:engineer|developer|designer)": "role",
            r"i(?:'m| am) (?:new to|learning|just started)": "experience_level:beginner",
            r"i(?:'ve| have) been (?:doing|working).*(?:years|decade)": "experience_level:advanced",
        }

        import re
        text = user_msg.lower()

        for pattern, field in identity_patterns.items():
            match = re.search(pattern, text)
            if match:
                if ":" in field:
                    field, value = field.split(":")
                else:
                    value = match.group(1).strip()

                self._update_identity_field(field, value, source="explicit")

        # Infer from communication style
        await self._infer_communication_style(user_msg)

    def _update_identity_field(self, field: str, value: str, source: str = "inferred"):
        """Update a single identity field with confidence tracking."""

        current = self.db.query_one("SELECT * FROM user_identity WHERE id = 1")

        if not current:
            self.db.insert("user_identity", {field: value})
            return

        current_value = getattr(current, field, None)

        # Explicit always wins
        if source == "explicit":
            self.db.execute(f"""
                UPDATE user_identity SET {field} = ?, updated_at = unixepoch() WHERE id = 1
            """, value)
            return

        # Don't overwrite explicit with inferred
        if current_value and source == "inferred":
            return

        # Update if empty or if this is explicit
        if not current_value:
            self.db.execute(f"""
                UPDATE user_identity SET {field} = ?, updated_at = unixepoch() WHERE id = 1
            """, value)

    async def _infer_communication_style(self, user_msg: str):
        """Infer user's communication preferences from their messages."""

        # Message length as verbosity signal
        word_count = len(user_msg.split())

        # Track in a rolling window
        self.db.insert("style_observations", {
            "observation_type": "message_length",
            "value": word_count,
        })

        # Periodically analyze
        recent = self.db.query("""
            SELECT AVG(value) as avg_length FROM style_observations
            WHERE observation_type = 'message_length'
            AND timestamp > unixepoch() - 86400
        """)

        if recent and recent[0].avg_length:
            avg = recent[0].avg_length
            if avg < 20:
                pref = "concise"
            elif avg > 100:
                pref = "detailed"
            else:
                pref = "balanced"

            self._update_identity_field("verbosity_preference", pref, "inferred")

    async def _extract_preferences(self, user_msg: str, assistant_msg: str):
        """Extract preferences from interaction."""

        # Use LLM to extract preferences (batched, not every message)
        extraction_prompt = """Analyze this interaction for user preferences.

Look for:
- Explicit preferences ("I prefer X", "I like Y", "Use Z")
- Corrections ("No, do it this way", "Actually I want...")
- Rejections ("Don't use X", "I don't like Y")
- Implicit preferences (how they write code, terminology they use)

Interaction:
User: {user_msg}
Assistant: {assistant_msg}

Return JSON array of preferences found (empty array if none):
[{{"domain": "...", "key": "...", "value": "...", "source": "explicit|implicit", "confidence": 0.0-1.0}}]

Only extract high-confidence preferences. Be conservative."""

        result = await self.llm.call(
            model="classifier",
            messages=[{"role": "user", "content": extraction_prompt.format(
                user_msg=user_msg[:1000],
                assistant_msg=assistant_msg[:1000]
            )}],
            response_format="json"
        )

        try:
            preferences = json.loads(result)
        except:
            return

        for pref in preferences:
            await self._store_preference(pref)

    async def _store_preference(self, pref: dict):
        """Store or update a preference."""
        domain = pref.get("domain", "general")
        key = pref.get("key")
        value = pref.get("value")
        confidence = pref.get("confidence", 0.5)
        source = pref.get("source", "inferred")

        if not key or not value:
            return

        # Check for existing preference
        existing = self.db.query_one("""
            SELECT * FROM user_preferences
            WHERE domain = ? AND key = ? AND active = 1
        """, domain, key)

        if existing:
            if existing.value == value:
                # Same preference - increase confidence
                self.db.execute("""
                    UPDATE user_preferences SET
                        confidence = MIN(0.95, confidence + 0.1),
                        evidence_count = evidence_count + 1,
                        last_confirmed = unixepoch()
                    WHERE id = ?
                """, existing.id)
            else:
                # Different value - potential contradiction
                if source == "explicit" or confidence > existing.confidence:
                    # New preference wins
                    self.db.execute("""
                        UPDATE user_preferences SET active = 0, contradicted_by = ?
                        WHERE id = ?
                    """, None, existing.id)  # Will update contradicted_by after insert

                    new_id = self.db.insert("user_preferences", {
                        "domain": domain,
                        "key": key,
                        "value": value,
                        "source": source,
                        "confidence": confidence,
                    })

                    self.db.execute("""
                        UPDATE user_preferences SET contradicted_by = ? WHERE id = ?
                    """, new_id, existing.id)
        else:
            # New preference
            self.db.insert("user_preferences", {
                "domain": domain,
                "key": key,
                "value": value,
                "source": source,
                "confidence": confidence,
            })

    async def _detect_project_context(self, user_msg: str, context: dict = None):
        """Detect and track project context."""

        # Check for mentioned paths
        import re
        path_pattern = r'(?:/[\w\-\.]+)+(?:/[\w\-\.]*)?'
        paths = re.findall(path_pattern, user_msg)

        for path in paths:
            await self._maybe_register_project(path, "mentioned")

        # Check current working directory from context
        if context and context.get("cwd"):
            await self._maybe_register_project(context["cwd"], "cwd")

    async def _maybe_register_project(self, path: str, detection_source: str):
        """Register a project if this path looks like one."""
        from pathlib import Path

        p = Path(path)
        if not p.exists():
            return

        # Look for project indicators
        project_indicators = [
            ".git", "package.json", "Cargo.toml", "CMakeLists.txt",
            "setup.py", "pyproject.toml", "Makefile", "README.md"
        ]

        # Walk up to find project root
        project_root = None
        current = p if p.is_dir() else p.parent

        for _ in range(5):  # Max 5 levels up
            for indicator in project_indicators:
                if (current / indicator).exists():
                    project_root = current
                    break
            if project_root:
                break
            current = current.parent

        if not project_root:
            return

        project_id = project_root.name.lower().replace(" ", "-")

        # Check if already registered
        existing = self.db.query_one("SELECT * FROM projects WHERE id = ?", project_id)

        if existing:
            # Update last active
            self.db.execute("""
                UPDATE projects SET
                    last_active = unixepoch(),
                    interaction_count = interaction_count + 1
                WHERE id = ?
            """, project_id)
        else:
            # Analyze and register new project
            project_info = await self._analyze_project(project_root)
            project_info["id"] = project_id
            project_info["path"] = str(project_root)
            project_info["auto_detected"] = 1
            project_info["detection_source"] = detection_source

            self.db.insert("projects", project_info)

    async def _analyze_project(self, path: Path) -> dict:
        """Analyze a project directory to extract metadata."""
        info = {
            "name": path.name,
            "languages": [],
            "frameworks": [],
        }

        # Detect languages by file extensions
        extensions = {}
        for f in path.rglob("*"):
            if f.is_file() and f.suffix:
                ext = f.suffix.lower()
                extensions[ext] = extensions.get(ext, 0) + 1

        ext_to_lang = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".rs": "rust", ".go": "go", ".cpp": "c++", ".c": "c",
            ".java": "java", ".rb": "ruby", ".swift": "swift",
        }

        languages = []
        for ext, count in sorted(extensions.items(), key=lambda x: -x[1])[:5]:
            if ext in ext_to_lang:
                languages.append(ext_to_lang[ext])

        info["languages"] = json.dumps(languages)

        # Detect frameworks
        frameworks = []
        framework_indicators = {
            "ros2": ["package.xml", "CMakeLists.txt"],  # If both present
            "react": ["package.json"],  # Check for react in deps
            "django": ["manage.py"],
            "fastapi": ["main.py"],  # Check imports
            "arduino": [".ino"],
        }

        if (path / "package.xml").exists():
            frameworks.append("ros2")
        if (path / "platformio.ini").exists():
            frameworks.append("platformio")

        info["frameworks"] = json.dumps(frameworks)

        # Detect build system
        if (path / "CMakeLists.txt").exists():
            info["build_system"] = "cmake"
        elif (path / "Cargo.toml").exists():
            info["build_system"] = "cargo"
        elif (path / "package.json").exists():
            info["build_system"] = "npm"
        elif (path / "setup.py").exists() or (path / "pyproject.toml").exists():
            info["build_system"] = "python"

        # Try to get description from README
        for readme in ["README.md", "README.rst", "README.txt", "README"]:
            readme_path = path / readme
            if readme_path.exists():
                try:
                    content = readme_path.read_text()[:500]
                    # First paragraph as description
                    lines = content.split("\n\n")
                    if len(lines) > 1:
                        info["description"] = lines[1][:200]
                except:
                    pass
                break

        return info

    def get_core_context(self) -> str:
        """Build core identity context for prompt injection."""
        identity = self.db.query_one("SELECT * FROM user_identity WHERE id = 1")

        prefs = self.db.query("""
            SELECT domain, key, value FROM user_preferences
            WHERE active = 1 AND confidence > 0.6
            ORDER BY confidence DESC LIMIT 15
        """)

        projects = self.db.query("""
            SELECT name, domain, status FROM projects
            WHERE status = 'active'
            ORDER BY last_active DESC LIMIT 5
        """)

        lines = []

        if identity:
            if identity.name:
                lines.append(f"User: {identity.name}")
            if identity.role:
                lines.append(f"Role: {identity.role}")
            if identity.primary_domain:
                lines.append(f"Domain: {identity.primary_domain}")
            if identity.verbosity_preference:
                lines.append(f"Communication: prefers {identity.verbosity_preference} responses")

        if prefs:
            lines.append("\nPreferences:")
            for p in prefs:
                lines.append(f"- [{p.domain}] {p.key}: {p.value}")

        if projects:
            lines.append("\nActive Projects:")
            for p in projects:
                lines.append(f"- {p.name} ({p.domain or 'general'})")

        return "\n".join(lines) if lines else "User profile not yet established."
```

---

## Part 3: Episodic Memory (With Vector Search)

```sql
-- Core memory table with embeddings
CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Content
    content TEXT NOT NULL,
    embedding BLOB,                     -- float32 vector, stored as blob

    -- Classification
    memory_type TEXT NOT NULL,          -- "interaction", "fact", "decision", "outcome", "observation", "summary"
    domain TEXT,                        -- "engineering", "health", "communication", etc.

    -- Importance (adaptive)
    importance REAL DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    last_accessed REAL,

    -- Temporal
    created_at REAL DEFAULT (unixepoch()),
    valid_from REAL,
    valid_to REAL,                      -- NULL = still valid

    -- Linking
    project_id TEXT REFERENCES projects(id),
    session_id TEXT,
    source TEXT DEFAULT 'internal',     -- "internal", "user", "external", "system"

    -- Deduplication
    entity_type TEXT,
    entity_id TEXT,
    superseded_by INTEGER REFERENCES memories(id),

    -- Summarization
    is_summary INTEGER DEFAULT 0,
    summarizes TEXT                     -- JSON array of memory IDs
);

-- For vector search (using sqlite-vec or similar)
-- This would be created by the vector extension
-- CREATE VIRTUAL TABLE memory_vectors USING vec0(embedding float[768]);

CREATE INDEX idx_memories_type ON memories(memory_type);
CREATE INDEX idx_memories_domain ON memories(domain);
CREATE INDEX idx_memories_importance ON memories(importance DESC);
CREATE INDEX idx_memories_project ON memories(project_id);
CREATE INDEX idx_memories_valid ON memories(valid_to) WHERE valid_to IS NULL;
CREATE INDEX idx_memories_entity ON memories(entity_type, entity_id) WHERE entity_type IS NOT NULL;
```

### Memory Operations

```python
# backend/memory_v2/episodic.py

import numpy as np
from typing import Optional
import json

class EpisodicMemory:
    """Episodic memory with vector search and adaptive importance."""

    def __init__(self, db, embedder, system_awareness):
        self.db = db
        self.embedder = embedder
        self.system = system_awareness
        self._vector_dim = 768  # Nomic embed dimension

    async def store(self, content: str, memory_type: str, domain: str = None,
                   project_id: str = None, entity_type: str = None,
                   entity_id: str = None, source: str = "internal",
                   importance: float = 0.5) -> int:
        """Store a memory with embedding."""

        # Generate embedding
        embedding = await self.embedder.embed(content)
        embedding_blob = np.array(embedding, dtype=np.float32).tobytes()

        # Check for supersession
        supersedes_id = None
        if entity_type and entity_id:
            existing = self.db.query_one("""
                SELECT id FROM memories
                WHERE entity_type = ? AND entity_id = ?
                AND superseded_by IS NULL AND valid_to IS NULL
            """, entity_type, entity_id)

            if existing:
                supersedes_id = existing.id

        # Insert memory
        memory_id = self.db.insert("memories", {
            "content": content,
            "embedding": embedding_blob,
            "memory_type": memory_type,
            "domain": domain,
            "project_id": project_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "source": source,
            "importance": importance,
        })

        # Mark superseded memory
        if supersedes_id:
            self.db.execute("""
                UPDATE memories SET
                    superseded_by = ?,
                    valid_to = unixepoch()
                WHERE id = ?
            """, memory_id, supersedes_id)

        return memory_id

    async def search(self, query: str, top_k: int = 10,
                    filters: dict = None) -> list[dict]:
        """Search memories by semantic similarity with optional filters."""

        # Get query embedding
        query_embedding = np.array(
            await self.embedder.embed(query),
            dtype=np.float32
        )

        # Build filter clause
        where_clauses = ["superseded_by IS NULL", "valid_to IS NULL"]
        params = []

        if filters:
            if filters.get("domain"):
                where_clauses.append("domain = ?")
                params.append(filters["domain"])
            if filters.get("domains"):
                placeholders = ",".join("?" * len(filters["domains"]))
                where_clauses.append(f"domain IN ({placeholders})")
                params.extend(filters["domains"])
            if filters.get("memory_type"):
                where_clauses.append("memory_type = ?")
                params.append(filters["memory_type"])
            if filters.get("project_id"):
                where_clauses.append("project_id = ?")
                params.append(filters["project_id"])
            if filters.get("min_importance"):
                where_clauses.append("importance >= ?")
                params.append(filters["min_importance"])

        where_sql = " AND ".join(where_clauses)

        # Fetch candidates (with vectors)
        rows = self.db.query(f"""
            SELECT id, content, embedding, memory_type, domain, importance, created_at
            FROM memories
            WHERE {where_sql}
            AND embedding IS NOT NULL
        """, *params)

        if not rows:
            return []

        # Compute similarities
        results = []
        for row in rows:
            mem_embedding = np.frombuffer(row.embedding, dtype=np.float32)

            # Cosine similarity
            similarity = np.dot(query_embedding, mem_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(mem_embedding) + 1e-10
            )

            # Combined score: similarity + importance boost
            score = similarity * 0.7 + row.importance * 0.3

            results.append({
                "id": row.id,
                "content": row.content,
                "memory_type": row.memory_type,
                "domain": row.domain,
                "importance": row.importance,
                "similarity": float(similarity),
                "score": float(score),
                "created_at": row.created_at,
            })

        # Sort by combined score
        results.sort(key=lambda x: x["score"], reverse=True)

        # Record access for top results
        for r in results[:top_k]:
            self._record_access(r["id"])

        return results[:top_k]

    def _record_access(self, memory_id: int):
        """Record access and boost importance."""
        self.db.execute("""
            UPDATE memories SET
                access_count = access_count + 1,
                last_accessed = unixepoch(),
                importance = MIN(0.95, importance + 0.03)
            WHERE id = ?
        """, memory_id)

    async def decay_importance(self):
        """Decay importance of unaccessed memories."""
        self.db.execute("""
            UPDATE memories SET
                importance = MAX(0.05, importance * 0.995)
            WHERE last_accessed < unixepoch() - 86400
            AND is_summary = 0
        """)

    async def consolidate(self, min_age_days: int = 30,
                         min_count: int = 5,
                         max_importance: float = 0.4):
        """Consolidate old low-importance memories into summaries."""

        # Find consolidation candidates grouped by domain
        candidates = self.db.query("""
            SELECT domain, COUNT(*) as count FROM memories
            WHERE created_at < unixepoch() - (? * 86400)
            AND is_summary = 0
            AND superseded_by IS NULL
            AND importance < ?
            GROUP BY domain
            HAVING count >= ?
        """, min_age_days, max_importance, min_count)

        for group in candidates:
            await self._consolidate_domain(group.domain, min_age_days, max_importance)

    async def _consolidate_domain(self, domain: str, min_age_days: int,
                                  max_importance: float):
        """Consolidate memories for a specific domain."""

        memories = self.db.query("""
            SELECT id, content, memory_type FROM memories
            WHERE domain = ?
            AND created_at < unixepoch() - (? * 86400)
            AND is_summary = 0
            AND superseded_by IS NULL
            AND importance < ?
            ORDER BY created_at
            LIMIT 20
        """, domain, min_age_days, max_importance)

        if len(memories) < 5:
            return

        # Create summary using LLM
        content = "\n".join(f"- {m.content}" for m in memories)

        summary = await self.llm.call(
            model="primary",
            messages=[{
                "role": "user",
                "content": f"""Summarize these {domain} observations into key points.
Preserve important facts and patterns. Be concise.

Observations:
{content}

Summary:"""
            }]
        )

        # Store summary
        summary_id = await self.store(
            content=summary,
            memory_type="summary",
            domain=domain,
            importance=0.6,
            source="consolidation"
        )

        # Update original memories
        memory_ids = [m.id for m in memories]
        self.db.execute(f"""
            UPDATE memories SET
                importance = 0.02
            WHERE id IN ({','.join('?' * len(memory_ids))})
        """, *memory_ids)

        # Record what was summarized
        self.db.execute("""
            UPDATE memories SET summarizes = ? WHERE id = ?
        """, json.dumps(memory_ids), summary_id)

    def count(self) -> int:
        """Count active memories."""
        return self.db.query_one(
            "SELECT COUNT(*) as c FROM memories WHERE superseded_by IS NULL"
        ).c

    def stats(self) -> dict:
        """Get memory statistics."""
        return {
            "total": self.db.query_one("SELECT COUNT(*) as c FROM memories").c,
            "active": self.count(),
            "summaries": self.db.query_one(
                "SELECT COUNT(*) as c FROM memories WHERE is_summary = 1"
            ).c,
            "by_domain": {
                row.domain: row.count for row in self.db.query("""
                    SELECT domain, COUNT(*) as count FROM memories
                    WHERE superseded_by IS NULL
                    GROUP BY domain
                """)
            },
            "by_type": {
                row.memory_type: row.count for row in self.db.query("""
                    SELECT memory_type, COUNT(*) as count FROM memories
                    WHERE superseded_by IS NULL
                    GROUP BY memory_type
                """)
            },
        }
```

---

## Part 4: Context Assembly

```python
# backend/memory_v2/context.py

class ContextBuilder:
    """Assembles tiered context for prompts."""

    def __init__(self, db, user_model, episodic_memory, system_awareness):
        self.db = db
        self.user_model = user_model
        self.memory = episodic_memory
        self.system = system_awareness

    async def build_context(self, query: str, session_id: str = None) -> dict:
        """Build complete context for a query."""

        # Get adaptive budget based on current resources
        budget = self.system.get_adaptive_context_budget()

        # Tier 1: Core identity (always included)
        core = self.user_model.get_core_context()
        core_tokens = self._count_tokens(core)

        # Tier 2: Session context
        session = ""
        if session_id:
            session = self._build_session_context(session_id, budget["session"])
        session_tokens = self._count_tokens(session)

        # Tier 3: Retrieved context
        remaining_budget = budget["retrieved"] - (core_tokens - budget["core"])
        retrieved = await self._retrieve_context(
            query, session_id, max_tokens=remaining_budget
        )
        retrieved_tokens = self._count_tokens(retrieved)

        # Assemble
        full_context = f"""{core}

{session}

{retrieved}""".strip()

        return {
            "context": full_context,
            "tokens": {
                "core": core_tokens,
                "session": session_tokens,
                "retrieved": retrieved_tokens,
                "total": core_tokens + session_tokens + retrieved_tokens,
                "budget": budget["total"],
            },
            "budget_info": budget,
        }

    def _build_session_context(self, session_id: str, max_tokens: int) -> str:
        """Build context from current session."""

        session = self.db.query_one(
            "SELECT * FROM sessions WHERE id = ?", session_id
        )

        if not session:
            return ""

        parts = []

        # Session summary if available
        if session.summary:
            parts.append(f"## Conversation Summary\n{session.summary}")

        # Recent messages
        messages = self.db.query("""
            SELECT role, content FROM session_messages
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT 10
        """, session_id)

        if messages:
            parts.append("## Recent Messages")
            for msg in reversed(messages):
                parts.append(f"{msg.role}: {msg.content[:300]}")

        # Active project context
        if session.active_project_id:
            project = self._get_project_context(session.active_project_id)
            if project:
                parts.append(f"## Active Project\n{project}")

        context = "\n\n".join(parts)

        # Truncate if over budget
        while self._count_tokens(context) > max_tokens and parts:
            parts.pop()
            context = "\n\n".join(parts)

        return context

    async def _retrieve_context(self, query: str, session_id: str = None,
                                max_tokens: int = 4000) -> str:
        """Retrieve relevant context for query."""

        parts = []
        token_count = 0

        # 1. Detect domains in query
        domains = await self._classify_domains(query)

        # 2. Get active project if in session
        project_id = None
        if session_id:
            session = self.db.query_one(
                "SELECT active_project_id FROM sessions WHERE id = ?",
                session_id
            )
            project_id = session.active_project_id if session else None

        # 3. Vector search for similar memories
        memories = await self.memory.search(
            query,
            top_k=15,
            filters={"domains": domains} if domains else None
        )

        if memories:
            parts.append("## Relevant Context")
            for mem in memories:
                content = f"- [{mem['memory_type']}] {mem['content']}"
                content_tokens = self._count_tokens(content)
                if token_count + content_tokens > max_tokens * 0.6:
                    break
                parts.append(content)
                token_count += content_tokens

        # 4. Project-specific knowledge
        if project_id:
            project_knowledge = self.db.query("""
                SELECT content, knowledge_type FROM project_knowledge
                WHERE project_id = ? AND valid_to IS NULL
                ORDER BY importance DESC LIMIT 5
            """, project_id)

            if project_knowledge:
                parts.append(f"\n## Project Knowledge")
                for pk in project_knowledge:
                    content = f"- [{pk.knowledge_type}] {pk.content}"
                    content_tokens = self._count_tokens(content)
                    if token_count + content_tokens > max_tokens * 0.8:
                        break
                    parts.append(content)
                    token_count += content_tokens

        # 5. Relevant patterns
        patterns = self.db.query("""
            SELECT description FROM patterns
            WHERE active = 1 AND confidence > 0.6
            ORDER BY confidence DESC LIMIT 3
        """)

        if patterns:
            parts.append("\n## Observed Patterns")
            for p in patterns:
                parts.append(f"- {p.description}")

        return "\n".join(parts)

    async def _classify_domains(self, query: str) -> list[str]:
        """Classify which domains a query relates to."""

        # Simple keyword-based for speed
        domain_keywords = {
            "engineering": ["code", "bug", "error", "function", "class", "api", "build", "compile", "test"],
            "robotics": ["ros", "robot", "sensor", "motor", "actuator", "slam", "navigation"],
            "health": ["sleep", "exercise", "energy", "tired", "health", "workout"],
            "communication": ["email", "message", "write", "draft", "respond"],
        }

        query_lower = query.lower()
        domains = []

        for domain, keywords in domain_keywords.items():
            if any(kw in query_lower for kw in keywords):
                domains.append(domain)

        return domains or ["general"]

    def _get_project_context(self, project_id: str) -> str:
        """Get context for a specific project."""

        project = self.db.query_one(
            "SELECT * FROM projects WHERE id = ?", project_id
        )

        if not project:
            return ""

        lines = [f"**{project.name}**"]

        if project.description:
            lines.append(project.description)

        if project.languages:
            languages = json.loads(project.languages)
            lines.append(f"Languages: {', '.join(languages)}")

        if project.frameworks:
            frameworks = json.loads(project.frameworks)
            lines.append(f"Frameworks: {', '.join(frameworks)}")

        return "\n".join(lines)

    def _count_tokens(self, text: str) -> int:
        """Estimate token count. ~4 chars per token."""
        return len(text) // 4
```

---

## Part 5: Integration

### Updated Core Initialization

```python
# In core.py __init__ or start()

async def start(self):
    # ... existing code ...

    # Initialize Memory V2
    from memory_v2 import (
        SystemAwareness,
        UserModel,
        EpisodicMemory,
        ContextBuilder
    )

    self.system_awareness = SystemAwareness(self.db)
    self.system_awareness.detect_hardware()

    self.user_model = UserModel(self.db, self.inference)
    self.episodic_memory = EpisodicMemory(
        self.db, self.memory, self.system_awareness  # Use existing embedder
    )
    self.context_builder = ContextBuilder(
        self.db, self.user_model, self.episodic_memory, self.system_awareness
    )

    # Start resource monitoring
    asyncio.create_task(self._monitor_resources())

    logger.info("Memory V2 initialized")
    logger.info("System: %s cores, %.1fGB RAM, context budget: %d tokens",
        self.system_awareness.get_profile().cpu_cores,
        self.system_awareness.get_profile().ram_total_gb,
        self.system_awareness.get_adaptive_context_budget()["total"]
    )

async def _monitor_resources(self):
    """Periodic resource monitoring."""
    while self._ready:
        self.system_awareness.snapshot_resources()
        self.system_awareness.inventory_processes()
        await asyncio.sleep(60)  # Every minute
```

### Updated Chat Flow

```python
async def chat(self, message: str, history: list = None, ...):
    # ... classification ...

    # Build context using Memory V2
    context_result = await self.context_builder.build_context(
        message,
        session_id=self._current_session_id
    )

    # Use context in system prompt
    system_prompt = f"""You are Moose, a personal AI assistant.

{context_result['context']}

Respond helpfully based on your understanding of the user."""

    # ... LLM call ...

    # Learn from interaction
    asyncio.create_task(
        self.user_model.learn_from_interaction(message, response, context)
    )
```

---

## File Structure

```
backend/
├── memory_v2/
│   ├── __init__.py           # Exports main classes
│   ├── schema.sql            # All CREATE TABLE statements
│   ├── system_awareness.py   # Hardware detection, resource monitoring
│   ├── user_model.py         # Self-populating user model
│   ├── episodic.py           # Vector memory with importance
│   ├── context.py            # Tiered context assembly
│   ├── extraction.py         # Fact extraction from interactions
│   ├── consolidation.py      # Memory compression
│   └── migration.py          # V1 → V2 migration
```

---

## Summary

This design gives Moose:

1. **Self-awareness** — Knows what hardware it's on, adapts context budgets
2. **Self-populating user model** — Learns through interaction, no config needed
3. **Adaptive retrieval** — Scales with available resources
4. **Compounding understanding** — More interactions = better, not slower
5. **Generic architecture** — Works for any user on any hardware

The system discovers:
- Its own capabilities (hardware, GPU, memory)
- The user's identity and preferences (through interaction)
- The user's projects (through file access and mentions)
- Patterns and knowledge (through accumulation)

All without requiring configuration.
