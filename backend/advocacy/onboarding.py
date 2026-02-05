"""
FamilyOnboarding — guided advocacy setup.

Triggered on:
  - First run with advocacy enabled
  - /setup-advocacy command
  - Adding a new family member

Conversation stages:
  1. "Tell me about yourself" → populates advocacy.user
  2. "What matters most?" → seeds Goal Graph
  3. "Anyone you trust in the loop?" → advocate network setup
  4. If advocate: channel and permissions
  5. If family: other household members
  6. Per-member age-appropriate setup

State persisted so it resumes if interrupted.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class OnboardingStage:
    INTRO = "intro"
    ABOUT_YOU = "about_you"
    GOALS = "goals"
    ADVOCATES = "advocates"
    ADVOCATE_DETAILS = "advocate_details"
    FAMILY = "family"
    FAMILY_MEMBER = "family_member"
    COMPLETE = "complete"


# Stage prompts for the conversation flow
STAGE_PROMPTS = {
    OnboardingStage.INTRO: (
        "I'd like to understand what matters to you so I can be more helpful over time. "
        "This is completely optional — you can skip any question or stop at any point. "
        "Shall we get started?"
    ),
    OnboardingStage.ABOUT_YOU: (
        "Tell me a bit about yourself — your name, what you do, "
        "anything you think would help me understand your world better."
    ),
    OnboardingStage.GOALS: (
        "What matters most to you right now? These could be big life goals, "
        "small daily priorities, or anything in between. "
        "I'll keep track of these and help you stay on course."
    ),
    OnboardingStage.ADVOCATES: (
        "Is there anyone you trust who you'd like in the loop? "
        "A partner, parent, coach, or therapist? They'd only see themes, "
        "never specific conversations — and you control what gets shared."
    ),
    OnboardingStage.ADVOCATE_DETAILS: (
        "Great. For {name}, how would you like me to reach them? "
        "(email, Slack, Telegram) And what topics should they be aware of?"
    ),
    OnboardingStage.FAMILY: (
        "Are there other household members who'll use this system? "
        "I can set up age-appropriate profiles for each person."
    ),
    OnboardingStage.FAMILY_MEMBER: (
        "Tell me about {name} — how old are they? "
        "I'll adjust my approach to be appropriate for their age."
    ),
    OnboardingStage.COMPLETE: (
        "All set! I'll learn more about your priorities over time "
        "through our conversations. You can always update these settings "
        "by saying '/setup-advocacy'."
    ),
}


class FamilyOnboarding:
    """Guided advocacy setup flow with persistent state."""

    def __init__(self, path: Path):
        self._path = path
        self._state: dict = {
            "stage": OnboardingStage.INTRO,
            "started_at": None,
            "completed_at": None,
            "user_data": {},
            "goals_data": [],
            "advocates_data": [],
            "family_data": [],
            "current_advocate_index": 0,
            "current_family_index": 0,
        }
        self._load()

    # ── Persistence ──

    def _load(self):
        if self._path.exists():
            try:
                self._state = json.loads(self._path.read_text())
                logger.info("[Onboarding] Loaded state (stage=%s)", self._state["stage"])
            except Exception as e:
                logger.error("[Onboarding] Load error: %s", e)

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._state, indent=2))

    # ── Properties ──

    @property
    def stage(self) -> str:
        return self._state["stage"]

    @property
    def is_complete(self) -> bool:
        return self._state["stage"] == OnboardingStage.COMPLETE

    @property
    def is_started(self) -> bool:
        return self._state.get("started_at") is not None

    # ── Flow Control ──

    def start(self) -> str:
        """Start or resume onboarding. Returns the current prompt."""
        if not self.is_started:
            self._state["started_at"] = datetime.now(timezone.utc).isoformat()
            self._state["stage"] = OnboardingStage.INTRO
            self._save()
        return self.get_current_prompt()

    def get_current_prompt(self) -> str:
        """Get the prompt for the current stage."""
        stage = self._state["stage"]
        prompt = STAGE_PROMPTS.get(stage, "")

        # Dynamic substitutions
        if stage == OnboardingStage.ADVOCATE_DETAILS:
            idx = self._state["current_advocate_index"]
            advocates = self._state.get("advocates_data", [])
            if idx < len(advocates):
                prompt = prompt.format(name=advocates[idx].get("name", "them"))

        if stage == OnboardingStage.FAMILY_MEMBER:
            idx = self._state["current_family_index"]
            family = self._state.get("family_data", [])
            if idx < len(family):
                prompt = prompt.format(name=family[idx].get("name", "them"))

        return prompt

    def process_response(self, response: str) -> dict:
        """Process a user response for the current stage.
        Returns {next_prompt, stage, complete}."""
        stage = self._state["stage"]

        if stage == OnboardingStage.INTRO:
            return self._handle_intro(response)
        elif stage == OnboardingStage.ABOUT_YOU:
            return self._handle_about_you(response)
        elif stage == OnboardingStage.GOALS:
            return self._handle_goals(response)
        elif stage == OnboardingStage.ADVOCATES:
            return self._handle_advocates(response)
        elif stage == OnboardingStage.ADVOCATE_DETAILS:
            return self._handle_advocate_details(response)
        elif stage == OnboardingStage.FAMILY:
            return self._handle_family(response)
        elif stage == OnboardingStage.FAMILY_MEMBER:
            return self._handle_family_member(response)
        else:
            return {"next_prompt": "", "stage": stage, "complete": True}

    def reset(self):
        """Reset onboarding to start over."""
        self._state = {
            "stage": OnboardingStage.INTRO,
            "started_at": None,
            "completed_at": None,
            "user_data": {},
            "goals_data": [],
            "advocates_data": [],
            "family_data": [],
            "current_advocate_index": 0,
            "current_family_index": 0,
        }
        self._save()

    # ── Stage Handlers ──

    def _handle_intro(self, response: str) -> dict:
        skip_words = {"no", "skip", "not now", "later", "nah"}
        if response.strip().lower() in skip_words:
            self._complete()
            return {
                "next_prompt": "No problem! You can set this up anytime with '/setup-advocacy'.",
                "stage": OnboardingStage.COMPLETE,
                "complete": True,
            }
        self._advance(OnboardingStage.ABOUT_YOU)
        return self._stage_result()

    def _handle_about_you(self, response: str) -> dict:
        self._state["user_data"]["raw_response"] = response
        # Extract name if it seems like they provided one
        words = response.strip().split()
        if len(words) <= 5:
            self._state["user_data"]["name"] = response.strip()
        self._advance(OnboardingStage.GOALS)
        return self._stage_result()

    def _handle_goals(self, response: str) -> dict:
        # Parse goals from response (simple: split on newlines/commas)
        goals = []
        for line in response.replace(",", "\n").split("\n"):
            line = line.strip().lstrip("-•* 0123456789.)")
            if line:
                goals.append(line)
        self._state["goals_data"] = goals
        self._advance(OnboardingStage.ADVOCATES)
        return self._stage_result()

    def _handle_advocates(self, response: str) -> dict:
        no_words = {"no", "none", "skip", "not now", "nah", "just me"}
        if response.strip().lower() in no_words:
            self._advance(OnboardingStage.FAMILY)
            return self._stage_result()

        # Parse advocate names
        advocates = []
        for name in response.replace(",", "\n").split("\n"):
            name = name.strip()
            if name:
                advocates.append({"name": name})
        self._state["advocates_data"] = advocates

        if advocates:
            self._state["current_advocate_index"] = 0
            self._advance(OnboardingStage.ADVOCATE_DETAILS)
        else:
            self._advance(OnboardingStage.FAMILY)
        return self._stage_result()

    def _handle_advocate_details(self, response: str) -> dict:
        idx = self._state["current_advocate_index"]
        advocates = self._state["advocates_data"]
        if idx < len(advocates):
            advocates[idx]["details"] = response

        # Move to next advocate or family
        if idx + 1 < len(advocates):
            self._state["current_advocate_index"] = idx + 1
            self._save()
        else:
            self._advance(OnboardingStage.FAMILY)
        return self._stage_result()

    def _handle_family(self, response: str) -> dict:
        no_words = {"no", "none", "skip", "not now", "nah", "just me"}
        if response.strip().lower() in no_words:
            self._complete()
            return self._stage_result()

        # Parse family member names
        members = []
        for name in response.replace(",", "\n").split("\n"):
            name = name.strip()
            if name:
                members.append({"name": name})
        self._state["family_data"] = members

        if members:
            self._state["current_family_index"] = 0
            self._advance(OnboardingStage.FAMILY_MEMBER)
        else:
            self._complete()
        return self._stage_result()

    def _handle_family_member(self, response: str) -> dict:
        idx = self._state["current_family_index"]
        family = self._state["family_data"]
        if idx < len(family):
            family[idx]["details"] = response
            # Try to extract age
            import re
            age_match = re.search(r'\b(\d{1,2})\b', response)
            if age_match:
                family[idx]["age"] = int(age_match.group(1))

        if idx + 1 < len(family):
            self._state["current_family_index"] = idx + 1
            self._save()
        else:
            self._complete()
        return self._stage_result()

    # ── Helpers ──

    def _advance(self, next_stage: str):
        self._state["stage"] = next_stage
        self._save()

    def _complete(self):
        self._state["stage"] = OnboardingStage.COMPLETE
        self._state["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def _stage_result(self) -> dict:
        return {
            "next_prompt": self.get_current_prompt(),
            "stage": self._state["stage"],
            "complete": self.is_complete,
        }

    # ── Data Access ──

    def get_collected_data(self) -> dict:
        """Return all collected onboarding data."""
        return {
            "user": self._state.get("user_data", {}),
            "goals": self._state.get("goals_data", []),
            "advocates": self._state.get("advocates_data", []),
            "family": self._state.get("family_data", []),
        }

    def get_status(self) -> dict:
        return {
            "stage": self._state["stage"],
            "started": self.is_started,
            "complete": self.is_complete,
        }
