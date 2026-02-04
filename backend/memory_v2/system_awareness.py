"""
System Awareness — Hardware detection and resource monitoring.

Moose knows what machine it's running on and adapts accordingly.
"""

import json
import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Optional imports - graceful degradation if not available
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil not installed - resource monitoring will be limited")


class SystemAwareness:
    """Detect and monitor the system Moose is running on."""

    def __init__(self, db):
        self.db = db
        self._profile: Optional[dict] = None
        self._inference_base_url = "http://localhost:1234"  # LM Studio default

    def set_inference_url(self, url: str):
        """Set the inference backend URL for model queries."""
        self._inference_base_url = url

    def detect_hardware(self) -> dict:
        """Detect hardware capabilities. Run once on startup."""
        profile = {
            "hostname": platform.node(),
            "os_type": platform.system().lower(),
            "os_version": platform.release(),
            "cpu_model": self._get_cpu_model(),
            "cpu_cores": self._get_cpu_cores(),
            "cpu_threads": self._get_cpu_threads(),
            "ram_total_gb": self._get_ram_total(),
            "disk_total_gb": self._get_disk_total(),
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
        profile["can_run_embeddings_locally"] = profile["ram_total_gb"] >= 8 if profile["ram_total_gb"] else True

        # Store in database
        self._upsert_profile(profile)
        self._profile = profile

        logger.info(
            "System detected: %s, %d cores, %.1fGB RAM, GPU: %s, context budget: %d",
            profile["cpu_model"][:30] if profile["cpu_model"] else "Unknown",
            profile["cpu_cores"] or 0,
            profile["ram_total_gb"] or 0,
            profile["gpu_model"] or "None",
            profile["recommended_context_tokens"] or 8000
        )

        return profile

    def _upsert_profile(self, profile: dict):
        """Insert or update system profile."""
        existing = self.db.execute(
            "SELECT id FROM system_profile WHERE id = 1"
        ).fetchone()

        if existing:
            # Update
            set_clause = ", ".join(f"{k} = ?" for k in profile.keys())
            self.db.execute(
                f"UPDATE system_profile SET {set_clause}, updated_at = unixepoch() WHERE id = 1",
                tuple(profile.values())
            )
        else:
            # Insert
            columns = ", ".join(profile.keys())
            placeholders = ", ".join("?" * len(profile))
            self.db.execute(
                f"INSERT INTO system_profile (id, {columns}) VALUES (1, {placeholders})",
                tuple(profile.values())
            )
        self.db.commit()

    def _get_cpu_model(self) -> str:
        """Get CPU model string."""
        if platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except Exception:
                pass

            # Try Apple Silicon
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "hw.chip"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except Exception:
                pass

        if platform.system() == "Linux":
            try:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line:
                            return line.split(":")[1].strip()
            except Exception:
                pass

        return platform.processor() or "Unknown"

    def _get_cpu_cores(self) -> int:
        """Get physical CPU cores."""
        if HAS_PSUTIL:
            return psutil.cpu_count(logical=False) or 1
        return 1

    def _get_cpu_threads(self) -> int:
        """Get logical CPU threads."""
        if HAS_PSUTIL:
            return psutil.cpu_count(logical=True) or 1
        return 1

    def _get_ram_total(self) -> float:
        """Get total RAM in GB."""
        if HAS_PSUTIL:
            return round(psutil.virtual_memory().total / (1024**3), 1)

        # Fallback for macOS
        if platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return round(int(result.stdout.strip()) / (1024**3), 1)
            except Exception:
                pass

        return 8.0  # Conservative default

    def _get_disk_total(self) -> float:
        """Get total disk space in GB."""
        if HAS_PSUTIL:
            return round(psutil.disk_usage('/').total / (1024**3), 1)
        return 100.0  # Default

    def _detect_gpu(self) -> dict:
        """Detect GPU model and VRAM."""
        result = {"gpu_model": None, "gpu_vram_gb": None}

        # macOS - check for Apple Silicon GPU
        if platform.system() == "Darwin":
            try:
                sp = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType", "-json"],
                    capture_output=True, text=True, timeout=10
                )
                if sp.returncode == 0:
                    data = json.loads(sp.stdout)
                    displays = data.get("SPDisplaysDataType", [])
                    if displays:
                        gpu = displays[0]
                        model = gpu.get("sppci_model", "")
                        if model:
                            result["gpu_model"] = model
                        elif gpu.get("spdisplays_vendor") == "sppci_vendor_apple":
                            result["gpu_model"] = "Apple Silicon GPU"
                        # Apple Silicon shares unified memory - VRAM is part of RAM
                        result["gpu_vram_gb"] = None
            except Exception as e:
                logger.debug("GPU detection (macOS) failed: %s", e)

        # NVIDIA GPU
        try:
            nvidia = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5
            )
            if nvidia.returncode == 0 and nvidia.stdout.strip():
                parts = nvidia.stdout.strip().split(", ")
                result["gpu_model"] = parts[0]
                if len(parts) > 1:
                    vram = parts[1].replace("MiB", "").strip()
                    result["gpu_vram_gb"] = round(int(vram) / 1024, 1)
        except Exception:
            pass

        # AMD GPU (Linux)
        if platform.system() == "Linux" and not result["gpu_model"]:
            try:
                rocm = subprocess.run(
                    ["rocm-smi", "--showproductname"],
                    capture_output=True, text=True, timeout=5
                )
                if rocm.returncode == 0 and rocm.stdout.strip():
                    for line in rocm.stdout.split("\n"):
                        if "GPU" in line:
                            result["gpu_model"] = line.strip()
                            break
            except Exception:
                pass

        return result

    def _has_neural_engine(self) -> bool:
        """Check for Apple Neural Engine (Apple Silicon)."""
        if platform.system() != "Darwin":
            return False
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.optional.arm64"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() == "1"
        except Exception:
            return False

    def _has_cuda(self) -> bool:
        """Check for CUDA support."""
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _has_rocm(self) -> bool:
        """Check for AMD ROCm support."""
        try:
            result = subprocess.run(
                ["rocm-smi"],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _calculate_max_model_size(self, profile: dict) -> float:
        """Calculate largest model that can reasonably run."""
        ram = profile.get("ram_total_gb") or 8
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
        ram = profile.get("ram_total_gb") or 8

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
        if not HAS_PSUTIL:
            return {}

        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else (0, 0, 0)

        snapshot = {
            "ram_used_gb": round((mem.total - mem.available) / (1024**3), 2),
            "ram_available_gb": round(mem.available / (1024**3), 2),
            "ram_percent": mem.percent,
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "load_avg_1m": load_avg[0],
            "load_avg_5m": load_avg[1],
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_available_gb": round(disk.free / (1024**3), 2),
        }

        # GPU usage (NVIDIA)
        try:
            nvidia = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if nvidia.returncode == 0 and nvidia.stdout.strip():
                parts = nvidia.stdout.strip().split(", ")
                snapshot["gpu_used_gb"] = round(int(parts[0]) / 1024, 2)
                snapshot["gpu_available_gb"] = round(int(parts[1]) / 1024, 2)
                snapshot["gpu_percent"] = float(parts[2])
        except Exception:
            pass

        # LM Studio loaded models
        snapshot["lm_studio_loaded_models"] = json.dumps(self._get_lm_studio_models())

        # Get memory entry count if table exists
        try:
            result = self.db.execute("SELECT COUNT(*) as c FROM memories").fetchone()
            snapshot["memory_entry_count"] = result[0] if result else 0
        except Exception:
            snapshot["memory_entry_count"] = 0

        # Store snapshot
        columns = ", ".join(snapshot.keys())
        placeholders = ", ".join("?" * len(snapshot))
        self.db.execute(
            f"INSERT INTO resource_snapshots ({columns}) VALUES ({placeholders})",
            tuple(snapshot.values())
        )
        self.db.commit()

        # Prune old snapshots (keep last 24 hours)
        self.db.execute(
            "DELETE FROM resource_snapshots WHERE timestamp < unixepoch() - 86400"
        )
        self.db.commit()

        return snapshot

    def _get_lm_studio_models(self) -> list:
        """Get currently loaded models from LM Studio."""
        try:
            import httpx
            resp = httpx.get(f"{self._inference_base_url}/v1/models", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception:
            pass
        return []

    def inventory_processes(self):
        """Inventory running processes and categorize them."""
        if not HAS_PSUTIL:
            return

        categories = {
            "lm-studio": "inference",
            "lm studio": "inference",
            "ollama": "inference",
            "llama": "inference",
            "python": "user_app",
            "node": "user_app",
            "code": "ide",
            "cursor": "ide",
            "vim": "ide",
            "nvim": "ide",
            "zed": "ide",
            "xcode": "ide",
            "chrome": "browser",
            "firefox": "browser",
            "safari": "browser",
            "arc": "browser",
        }

        seen_pids = set()

        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info']):
            try:
                info = proc.info
                pid = info['pid']
                seen_pids.add(pid)

                name = (info['name'] or '').lower()

                # Categorize
                category = "system"
                for pattern, cat in categories.items():
                    if pattern in name:
                        category = cat
                        break

                memory_mb = 0
                if info.get('memory_info'):
                    memory_mb = round(info['memory_info'].rss / (1024**2), 1)

                cmdline = ''
                if info.get('cmdline'):
                    cmdline = ' '.join(info['cmdline'])[:500]

                # Upsert
                existing = self.db.execute(
                    "SELECT id FROM process_inventory WHERE pid = ?", (pid,)
                ).fetchone()

                if existing:
                    self.db.execute("""
                        UPDATE process_inventory SET
                            name = ?, cmdline = ?, cpu_percent = ?,
                            memory_mb = ?, category = ?, last_seen = unixepoch()
                        WHERE pid = ?
                    """, (info['name'], cmdline, info.get('cpu_percent', 0),
                        memory_mb, category, pid))
                else:
                    self.db.execute("""
                        INSERT INTO process_inventory
                        (pid, name, cmdline, cpu_percent, memory_mb, category)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (pid, info['name'], cmdline, info.get('cpu_percent', 0),
                        memory_mb, category))

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Remove stale processes (not seen in 5 minutes)
        self.db.execute(
            "DELETE FROM process_inventory WHERE last_seen < unixepoch() - 300"
        )
        self.db.commit()

    def get_profile(self) -> Optional[dict]:
        """Get cached system profile."""
        if self._profile:
            return self._profile

        row = self.db.execute(
            "SELECT * FROM system_profile WHERE id = 1"
        ).fetchone()

        if row:
            # Convert row to dict
            columns = [desc[0] for desc in self.db.execute(
                "SELECT * FROM system_profile LIMIT 0"
            ).description]
            self._profile = dict(zip(columns, row))

        return self._profile

    def get_adaptive_context_budget(self) -> dict:
        """Get context budget adapted to current resource availability."""
        profile = self.get_profile()
        base_budget = (profile or {}).get("recommended_context_tokens", 8000)

        # Get latest resource snapshot
        row = self.db.execute("""
            SELECT * FROM resource_snapshots ORDER BY timestamp DESC LIMIT 1
        """).fetchone()

        if not row:
            return {
                "total": base_budget,
                "core": 500,
                "session": min(4000, int(base_budget * 0.3)),
                "retrieved": base_budget - 500 - min(4000, int(base_budget * 0.3)),
                "multiplier": 1.0,
                "reason": "No resource data"
            }

        # Get column names
        columns = [desc[0] for desc in self.db.execute(
            "SELECT * FROM resource_snapshots LIMIT 0"
        ).description]
        snapshot = dict(zip(columns, row))

        # Adjust based on current availability
        ram_pressure = snapshot.get("ram_percent", 50) / 100

        if ram_pressure > 0.9:
            # System under heavy load - minimize context
            multiplier = 0.5
            reason = f"High memory pressure ({ram_pressure:.0%})"
        elif ram_pressure > 0.7:
            # Moderate load - reduce context
            multiplier = 0.75
            reason = f"Moderate memory usage ({ram_pressure:.0%})"
        else:
            # Normal - full budget
            multiplier = 1.0
            reason = f"Normal operation ({ram_pressure:.0%} RAM)"

        adjusted_budget = int(base_budget * multiplier)

        return {
            "total": adjusted_budget,
            "core": 500,  # Core identity is always small
            "session": min(4000, int(adjusted_budget * 0.3)),
            "retrieved": adjusted_budget - 500 - min(4000, int(adjusted_budget * 0.3)),
            "multiplier": multiplier,
            "reason": reason
        }

    def get_resource_summary(self) -> dict:
        """Get a human-readable summary of system resources."""
        profile = self.get_profile() or {}
        budget = self.get_adaptive_context_budget()

        # Latest snapshot
        row = self.db.execute("""
            SELECT ram_percent, cpu_percent, gpu_percent
            FROM resource_snapshots
            ORDER BY timestamp DESC LIMIT 1
        """).fetchone()

        snapshot = {}
        if row:
            snapshot = {
                "ram_percent": row[0],
                "cpu_percent": row[1],
                "gpu_percent": row[2],
            }

        return {
            "hardware": {
                "cpu": profile.get("cpu_model", "Unknown"),
                "cores": profile.get("cpu_cores", 0),
                "ram_gb": profile.get("ram_total_gb", 0),
                "gpu": profile.get("gpu_model"),
            },
            "capabilities": {
                "cuda": profile.get("has_cuda", False),
                "metal": profile.get("has_metal", False),
                "neural_engine": profile.get("has_neural_engine", False),
                "max_model_gb": profile.get("max_model_size_gb", 0),
            },
            "current_usage": snapshot,
            "context_budget": budget,
        }
