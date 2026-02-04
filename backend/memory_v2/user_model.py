"""
User Model — Self-populating user understanding.

Learns about the user through interaction, not configuration.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


class UserModel:
    """Self-populating user model that learns through interaction."""

    def __init__(self, db, llm_client: Callable[..., Awaitable[str]] = None):
        """
        Initialize user model.

        Args:
            db: Database connection
            llm_client: Async function to call LLM for extraction.
                       Signature: async (model: str, messages: list, **kwargs) -> str
        """
        self.db = db
        self._llm = llm_client

    def set_llm_client(self, llm_client: Callable[..., Awaitable[str]]):
        """Set the LLM client after initialization."""
        self._llm = llm_client

    async def learn_from_interaction(self, user_msg: str, assistant_msg: str,
                                     context: dict = None):
        """Extract learnings from an interaction."""
        # 1. Identity signals (fast, regex-based)
        self._update_identity_from_message(user_msg)

        # 2. Track communication style
        self._track_style_observation(user_msg)

        # 3. Project detection
        await self._detect_project_context(user_msg, context)

        # 4. Queue for deeper extraction (async, won't block)
        self._queue_for_extraction(user_msg, assistant_msg, context)

    def _update_identity_from_message(self, user_msg: str):
        """Update identity based on explicit statements in message."""
        text = user_msg.lower()

        # Patterns for identity extraction
        patterns = [
            # Name patterns
            (r"(?:my name is|i'm|i am|call me) ([a-z]+)", "name"),
            (r"(?:this is|it's) ([a-z]+) here", "name"),

            # Role patterns
            (r"i(?:'m| am) (?:a |an )?(.+?)(?:engineer|developer|designer|architect)",
             "role", lambda m: m.group(1).strip() + " " + m.group(0).split()[-1]),
            (r"i work as (?:a |an )?(.+?)(?:\.|,|$)", "role"),
            (r"my job is (.+?)(?:\.|,|$)", "role"),

            # Experience patterns
            (r"i(?:'m| am) (?:new to|learning|just started)", "experience_level", "beginner"),
            (r"i(?:'ve| have) been (?:doing|working).*(?:for years|decade|long time)",
             "experience_level", "advanced"),
            (r"i(?:'m| am) (?:a |an )?(?:senior|lead|principal)", "experience_level", "expert"),
            (r"i(?:'m| am) (?:a |an )?(?:junior|entry)", "experience_level", "beginner"),

            # Domain patterns
            (r"i (?:work on|build|develop) (.+?)(?:robots?|robotics)", "primary_domain", "robotics"),
            (r"i (?:work on|build|develop) (.+?)(?:web|websites?|apps?)", "primary_domain", "web"),
            (r"i (?:work on|build|develop) (.+?)(?:ml|machine learning|ai)", "primary_domain", "ml"),
            (r"i (?:work on|build|develop) (.+?)(?:embedded|firmware|hardware)",
             "primary_domain", "embedded"),
        ]

        for pattern_tuple in patterns:
            if len(pattern_tuple) == 2:
                pattern, field = pattern_tuple
                extractor = None
            elif len(pattern_tuple) == 3:
                pattern, field, extractor = pattern_tuple
            else:
                continue

            match = re.search(pattern, text)
            if match:
                if callable(extractor):
                    value = extractor(match)
                elif isinstance(extractor, str):
                    value = extractor
                else:
                    value = match.group(1).strip()

                if value:
                    self._update_identity_field(field, value, source="explicit")

    def _update_identity_field(self, field: str, value: str, source: str = "inferred"):
        """Update a single identity field with confidence tracking."""
        # Ensure user_identity row exists
        existing = self.db.execute(
            "SELECT * FROM user_identity WHERE id = 1"
        ).fetchone()

        if not existing:
            self.db.execute(
                "INSERT INTO user_identity (id) VALUES (1)"
            )
            self.db.commit()
            existing = self.db.execute(
                "SELECT * FROM user_identity WHERE id = 1"
            ).fetchone()

        # Get column names
        columns = [desc[0] for desc in self.db.execute(
            "SELECT * FROM user_identity LIMIT 0"
        ).description]

        if field not in columns:
            logger.warning("Unknown identity field: %s", field)
            return

        current_idx = columns.index(field)
        current_value = existing[current_idx] if existing else None

        # Explicit always wins
        if source == "explicit" or not current_value:
            self.db.execute(
                f"UPDATE user_identity SET {field} = ?, updated_at = unixepoch() WHERE id = 1",
                (value,)
            )
            self.db.commit()
            logger.info("Updated identity.%s = %s (source: %s)", field, value, source)

    def _track_style_observation(self, user_msg: str):
        """Track communication style observations."""
        # Message length
        word_count = len(user_msg.split())
        self.db.execute(
            "INSERT INTO style_observations (observation_type, value) VALUES (?, ?)",
            ("message_length", word_count)
        )

        # Formality signals
        formal_markers = ["please", "would you", "could you", "thank you", "appreciate"]
        casual_markers = ["hey", "yo", "gonna", "wanna", "lol", "haha"]

        formal_count = sum(1 for m in formal_markers if m in user_msg.lower())
        casual_count = sum(1 for m in casual_markers if m in user_msg.lower())

        if formal_count > casual_count:
            self.db.execute(
                "INSERT INTO style_observations (observation_type, value) VALUES (?, ?)",
                ("formality", 1.0)
            )
        elif casual_count > formal_count:
            self.db.execute(
                "INSERT INTO style_observations (observation_type, value) VALUES (?, ?)",
                ("formality", -1.0)
            )

        self.db.commit()

        # Periodically update identity based on accumulated observations
        self._update_style_preferences()

    def _update_style_preferences(self):
        """Update identity based on accumulated style observations."""
        # Check if we have enough observations (every 20 messages)
        count = self.db.execute(
            "SELECT COUNT(*) FROM style_observations WHERE observation_type = 'message_length'"
        ).fetchone()[0]

        if count < 20 or count % 20 != 0:
            return

        # Analyze message length
        avg = self.db.execute("""
            SELECT AVG(value) FROM style_observations
            WHERE observation_type = 'message_length'
            AND timestamp > unixepoch() - 86400
        """).fetchone()[0]

        if avg:
            if avg < 20:
                pref = "concise"
            elif avg > 100:
                pref = "detailed"
            else:
                pref = "balanced"
            self._update_identity_field("verbosity_preference", pref, "inferred")

        # Analyze formality
        formality = self.db.execute("""
            SELECT AVG(value) FROM style_observations
            WHERE observation_type = 'formality'
            AND timestamp > unixepoch() - 86400
        """).fetchone()[0]

        if formality is not None:
            if formality > 0.3:
                level = "professional"
            elif formality < -0.3:
                level = "casual"
            else:
                level = "mixed"
            self._update_identity_field("formality_level", level, "inferred")

    async def _detect_project_context(self, user_msg: str, context: dict = None):
        """Detect and track project context."""
        # Check for mentioned paths
        path_pattern = r'(?:/[\w\-\.]+)+(?:/[\w\-\.]*)?'
        paths = re.findall(path_pattern, user_msg)

        for path in paths:
            await self._maybe_register_project(path, "mentioned")

        # Check current working directory from context
        if context and context.get("cwd"):
            await self._maybe_register_project(context["cwd"], "cwd")

        # Check for project name mentions against known projects
        projects = self.db.execute(
            "SELECT id, name FROM projects WHERE status = 'active'"
        ).fetchall()

        msg_lower = user_msg.lower()
        for project_id, name in projects:
            if name and name.lower() in msg_lower:
                # Update last active
                self.db.execute("""
                    UPDATE projects SET
                        last_active = unixepoch(),
                        interaction_count = interaction_count + 1
                    WHERE id = ?
                """, (project_id,))
                self.db.commit()

    async def _maybe_register_project(self, path: str, detection_source: str):
        """Register a project if this path looks like one."""
        p = Path(path)
        if not p.exists():
            return

        # Look for project indicators
        project_indicators = [
            ".git", "package.json", "Cargo.toml", "CMakeLists.txt",
            "setup.py", "pyproject.toml", "Makefile", "README.md",
            "go.mod", "build.gradle", "pom.xml", "platformio.ini"
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
            if current.parent == current:  # Reached root
                break
            current = current.parent

        if not project_root:
            return

        project_id = project_root.name.lower().replace(" ", "-").replace("_", "-")

        # Check if already registered
        existing = self.db.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone()

        if existing:
            # Update last active
            self.db.execute("""
                UPDATE projects SET
                    last_active = unixepoch(),
                    interaction_count = interaction_count + 1
                WHERE id = ?
            """, (project_id,))
            self.db.commit()
        else:
            # Analyze and register new project
            project_info = self._analyze_project(project_root)
            project_info["id"] = project_id
            project_info["path"] = str(project_root)
            project_info["auto_detected"] = 1
            project_info["detection_source"] = detection_source

            columns = ", ".join(project_info.keys())
            placeholders = ", ".join("?" * len(project_info))
            self.db.execute(
                f"INSERT INTO projects ({columns}) VALUES ({placeholders})",
                tuple(project_info.values())
            )
            self.db.commit()
            logger.info("Registered project: %s at %s", project_id, project_root)

    def _analyze_project(self, path: Path) -> dict:
        """Analyze a project directory to extract metadata."""
        info = {
            "name": path.name,
            "languages": "[]",
            "frameworks": "[]",
        }

        # Detect languages by file extensions
        extensions = {}
        try:
            for f in path.rglob("*"):
                if f.is_file() and f.suffix:
                    ext = f.suffix.lower()
                    extensions[ext] = extensions.get(ext, 0) + 1
        except PermissionError:
            pass

        ext_to_lang = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".rs": "rust", ".go": "go", ".cpp": "c++", ".c": "c",
            ".java": "java", ".rb": "ruby", ".swift": "swift",
            ".kt": "kotlin", ".cs": "csharp", ".php": "php",
            ".ino": "arduino", ".h": "c/c++",
        }

        languages = []
        for ext, count in sorted(extensions.items(), key=lambda x: -x[1])[:5]:
            if ext in ext_to_lang:
                lang = ext_to_lang[ext]
                if lang not in languages:
                    languages.append(lang)

        info["languages"] = json.dumps(languages[:5])

        # Detect frameworks
        frameworks = []

        # ROS2
        if (path / "package.xml").exists():
            frameworks.append("ros2")

        # PlatformIO
        if (path / "platformio.ini").exists():
            frameworks.append("platformio")

        # Node.js frameworks
        if (path / "package.json").exists():
            try:
                pkg = json.loads((path / "package.json").read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "react" in deps:
                    frameworks.append("react")
                if "next" in deps:
                    frameworks.append("nextjs")
                if "vue" in deps:
                    frameworks.append("vue")
                if "express" in deps:
                    frameworks.append("express")
            except Exception:
                pass

        # Python frameworks
        for req_file in ["requirements.txt", "pyproject.toml", "setup.py"]:
            req_path = path / req_file
            if req_path.exists():
                try:
                    content = req_path.read_text().lower()
                    if "django" in content:
                        frameworks.append("django")
                    if "fastapi" in content:
                        frameworks.append("fastapi")
                    if "flask" in content:
                        frameworks.append("flask")
                    if "pytorch" in content or "torch" in content:
                        frameworks.append("pytorch")
                    if "tensorflow" in content:
                        frameworks.append("tensorflow")
                except Exception:
                    pass

        info["frameworks"] = json.dumps(list(set(frameworks)))

        # Detect build system
        if (path / "CMakeLists.txt").exists():
            info["build_system"] = "cmake"
        elif (path / "Cargo.toml").exists():
            info["build_system"] = "cargo"
        elif (path / "package.json").exists():
            info["build_system"] = "npm"
        elif (path / "go.mod").exists():
            info["build_system"] = "go"
        elif (path / "setup.py").exists() or (path / "pyproject.toml").exists():
            info["build_system"] = "python"
        elif (path / "Makefile").exists():
            info["build_system"] = "make"
        elif (path / "build.gradle").exists() or (path / "build.gradle.kts").exists():
            info["build_system"] = "gradle"
        elif (path / "platformio.ini").exists():
            info["build_system"] = "platformio"

        # Try to get description from README
        for readme in ["README.md", "README.rst", "README.txt", "README"]:
            readme_path = path / readme
            if readme_path.exists():
                try:
                    content = readme_path.read_text()[:1000]
                    # Skip title line(s) and get first paragraph
                    lines = content.split("\n")
                    description_lines = []
                    started = False
                    for line in lines:
                        stripped = line.strip()
                        # Skip empty lines and headers at the start
                        if not started:
                            if stripped and not stripped.startswith("#") and not stripped.startswith("="):
                                started = True
                                description_lines.append(stripped)
                        else:
                            if not stripped:
                                break
                            description_lines.append(stripped)

                    if description_lines:
                        info["description"] = " ".join(description_lines)[:300]
                except Exception:
                    pass
                break

        # Detect domain from frameworks/languages
        if "ros2" in frameworks or "robotics" in str(path).lower():
            info["domain"] = "robotics"
        elif "platformio" in frameworks or "arduino" in languages:
            info["domain"] = "embedded"
        elif any(f in frameworks for f in ["react", "vue", "nextjs", "express", "django", "fastapi"]):
            info["domain"] = "web"
        elif any(f in frameworks for f in ["pytorch", "tensorflow"]):
            info["domain"] = "ml"
        elif "rust" in languages:
            info["domain"] = "systems"

        # Git remote URL
        git_config = path / ".git" / "config"
        if git_config.exists():
            try:
                content = git_config.read_text()
                match = re.search(r'url = (.+)', content)
                if match:
                    info["repo_url"] = match.group(1).strip()
            except Exception:
                pass

        return info

    def _queue_for_extraction(self, user_msg: str, assistant_msg: str,
                             context: dict = None):
        """Queue interaction for async fact extraction."""
        self.db.execute("""
            INSERT INTO extraction_queue
            (user_message, assistant_message, context)
            VALUES (?, ?, ?)
        """, (user_msg, assistant_msg, json.dumps(context) if context else None))
        self.db.commit()

    async def process_extraction_queue(self, batch_size: int = 5):
        """Process pending extractions. Call periodically from cognitive loop."""
        if not self._llm:
            logger.warning("No LLM client configured for extraction")
            return

        pending = self.db.execute("""
            SELECT id, user_message, assistant_message, context
            FROM extraction_queue
            WHERE status = 'pending'
            ORDER BY created_at
            LIMIT ?
        """, (batch_size,)).fetchall()

        for row in pending:
            queue_id, user_msg, assistant_msg, context_json = row

            # Mark as processing
            self.db.execute(
                "UPDATE extraction_queue SET status = 'processing' WHERE id = ?",
                (queue_id,)
            )
            self.db.commit()

            try:
                await self._extract_preferences(user_msg, assistant_msg)

                # Mark completed
                self.db.execute("""
                    UPDATE extraction_queue
                    SET status = 'completed', processed_at = unixepoch()
                    WHERE id = ?
                """, (queue_id,))
            except Exception as e:
                logger.warning("Extraction failed for queue item %d: %s", queue_id, e)
                self.db.execute(
                    "UPDATE extraction_queue SET status = 'failed' WHERE id = ?",
                    (queue_id,)
                )

            self.db.commit()

        # Prune old completed items (keep last 1000)
        self.db.execute("""
            DELETE FROM extraction_queue
            WHERE status = 'completed'
            AND id NOT IN (
                SELECT id FROM extraction_queue
                WHERE status = 'completed'
                ORDER BY processed_at DESC
                LIMIT 1000
            )
        """)
        self.db.commit()

    async def _extract_preferences(self, user_msg: str, assistant_msg: str):
        """Extract preferences from interaction using LLM."""
        extraction_prompt = """Analyze this interaction for user preferences.

Look for:
- Explicit preferences ("I prefer X", "I like Y", "Use Z", "Always do X")
- Corrections ("No, do it this way", "Actually I want...", "Not like that")
- Rejections ("Don't use X", "I don't like Y", "Never do Z")
- Implicit preferences (coding style, terminology, approach)

Interaction:
User: {user_msg}
Assistant: {assistant_msg}

Return a JSON array of preferences found. Return [] if none found.
Each preference should have:
- domain: "code", "tools", "communication", "workflow", or "general"
- key: specific preference name (e.g., "naming_convention", "error_handling")
- value: the preference value
- source: "explicit" if directly stated, "implicit" if inferred
- confidence: 0.0-1.0

Only extract clear, actionable preferences. Be conservative."""

        try:
            result = await self._llm(
                model="classifier",  # Use fast model
                messages=[{
                    "role": "user",
                    "content": extraction_prompt.format(
                        user_msg=user_msg[:1000],
                        assistant_msg=assistant_msg[:1000]
                    )
                }]
            )

            # Parse JSON from response
            # Try to extract JSON array from response
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                preferences = json.loads(json_match.group())
            else:
                return

            for pref in preferences:
                await self._store_preference(pref)

        except json.JSONDecodeError:
            logger.debug("Failed to parse preference extraction result")
        except Exception as e:
            logger.warning("Preference extraction failed: %s", e)

    async def _store_preference(self, pref: dict):
        """Store or update a preference."""
        domain = pref.get("domain", "general")
        key = pref.get("key")
        value = pref.get("value")
        confidence = pref.get("confidence", 0.5)
        source = pref.get("source", "inferred")

        if not key or not value:
            return

        # Normalize
        key = key.lower().replace(" ", "_")

        # Check for existing preference
        existing = self.db.execute("""
            SELECT id, value, confidence, source FROM user_preferences
            WHERE domain = ? AND key = ? AND active = 1
        """, (domain, key)).fetchone()

        if existing:
            existing_id, existing_value, existing_conf, existing_source = existing

            if existing_value == value:
                # Same preference - increase confidence
                self.db.execute("""
                    UPDATE user_preferences SET
                        confidence = MIN(0.95, confidence + 0.1),
                        evidence_count = evidence_count + 1,
                        last_confirmed = unixepoch()
                    WHERE id = ?
                """, (existing_id,))
                logger.debug("Strengthened preference: %s.%s", domain, key)
            else:
                # Different value - potential contradiction
                # Explicit wins over inferred, higher confidence wins
                should_replace = (
                    (source == "explicit" and existing_source != "explicit") or
                    (source == existing_source and confidence > existing_conf)
                )

                if should_replace:
                    # Deactivate old preference
                    self.db.execute("""
                        UPDATE user_preferences SET active = 0 WHERE id = ?
                    """, (existing_id,))

                    # Insert new preference
                    self.db.execute("""
                        INSERT INTO user_preferences
                        (domain, key, value, source, confidence)
                        VALUES (?, ?, ?, ?, ?)
                    """, (domain, key, value, source, confidence))

                    # Update contradicted_by
                    new_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
                    self.db.execute("""
                        UPDATE user_preferences SET contradicted_by = ? WHERE id = ?
                    """, (new_id, existing_id))

                    logger.info("Updated preference: %s.%s = %s (was: %s)",
                               domain, key, value, existing_value)
        else:
            # New preference
            self.db.execute("""
                INSERT INTO user_preferences
                (domain, key, value, source, confidence)
                VALUES (?, ?, ?, ?, ?)
            """, (domain, key, value, source, confidence))
            logger.info("New preference: %s.%s = %s", domain, key, value)

        self.db.commit()

    def get_core_context(self) -> str:
        """Build core identity context for prompt injection."""
        lines = []

        # Identity
        identity = self.db.execute(
            "SELECT * FROM user_identity WHERE id = 1"
        ).fetchone()

        if identity:
            columns = [desc[0] for desc in self.db.execute(
                "SELECT * FROM user_identity LIMIT 0"
            ).description]
            identity_dict = dict(zip(columns, identity))

            if identity_dict.get("name"):
                name = identity_dict.get("preferred_name") or identity_dict.get("name")
                lines.append(f"User: {name}")
            if identity_dict.get("role"):
                lines.append(f"Role: {identity_dict['role']}")
            if identity_dict.get("primary_domain"):
                lines.append(f"Domain: {identity_dict['primary_domain']}")
            if identity_dict.get("experience_level"):
                lines.append(f"Experience: {identity_dict['experience_level']}")
            if identity_dict.get("verbosity_preference"):
                lines.append(f"Prefers {identity_dict['verbosity_preference']} responses")

        # Top preferences
        prefs = self.db.execute("""
            SELECT domain, key, value FROM user_preferences
            WHERE active = 1 AND confidence > 0.6
            ORDER BY confidence DESC LIMIT 10
        """).fetchall()

        if prefs:
            lines.append("\nPreferences:")
            for domain, key, value in prefs:
                lines.append(f"- [{domain}] {key}: {value}")

        # Active projects
        projects = self.db.execute("""
            SELECT name, domain, status FROM projects
            WHERE status = 'active'
            ORDER BY last_active DESC LIMIT 5
        """).fetchall()

        if projects:
            lines.append("\nActive Projects:")
            for name, domain, status in projects:
                domain_str = f" ({domain})" if domain else ""
                lines.append(f"- {name}{domain_str}")

        return "\n".join(lines) if lines else ""

    def get_identity(self) -> Optional[dict]:
        """Get current user identity."""
        row = self.db.execute(
            "SELECT * FROM user_identity WHERE id = 1"
        ).fetchone()

        if not row:
            return None

        columns = [desc[0] for desc in self.db.execute(
            "SELECT * FROM user_identity LIMIT 0"
        ).description]
        return dict(zip(columns, row))

    def get_preferences(self, domain: str = None) -> list[dict]:
        """Get active preferences, optionally filtered by domain."""
        if domain:
            rows = self.db.execute("""
                SELECT domain, key, value, confidence, source
                FROM user_preferences
                WHERE active = 1 AND domain = ?
                ORDER BY confidence DESC
            """, (domain,)).fetchall()
        else:
            rows = self.db.execute("""
                SELECT domain, key, value, confidence, source
                FROM user_preferences
                WHERE active = 1
                ORDER BY confidence DESC
            """).fetchall()

        return [
            {"domain": r[0], "key": r[1], "value": r[2],
             "confidence": r[3], "source": r[4]}
            for r in rows
        ]

    def get_active_projects(self) -> list[dict]:
        """Get active projects."""
        rows = self.db.execute("""
            SELECT id, name, path, domain, languages, frameworks, build_system
            FROM projects
            WHERE status = 'active'
            ORDER BY last_active DESC
        """).fetchall()

        return [
            {
                "id": r[0], "name": r[1], "path": r[2], "domain": r[3],
                "languages": json.loads(r[4]) if r[4] else [],
                "frameworks": json.loads(r[5]) if r[5] else [],
                "build_system": r[6]
            }
            for r in rows
        ]

    def set_preference(self, domain: str, key: str, value: str):
        """Explicitly set a preference (from user command)."""
        # Deactivate existing
        self.db.execute("""
            UPDATE user_preferences SET active = 0
            WHERE domain = ? AND key = ? AND active = 1
        """, (domain, key))

        # Insert new
        self.db.execute("""
            INSERT INTO user_preferences
            (domain, key, value, source, confidence)
            VALUES (?, ?, ?, 'explicit', 0.95)
        """, (domain, key, value))

        self.db.commit()
        logger.info("Set preference: %s.%s = %s", domain, key, value)

    def set_identity_field(self, field: str, value: str):
        """Explicitly set an identity field (from user command)."""
        self._update_identity_field(field, value, source="explicit")
