"""Bounded offline command matching. No execution, I/O or automatic cloud fallback."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping
from datetime import tzinfo
from typing import Any

from rapidfuzz.distance import Levenshtein

from agent.contracts.plan import Plan, PlanStep
from agent.interfaces import Clock
from agent.interfaces.models import KeywordResult
from agent.planner.validation import PlanValidationError, validate_plan
from agent.tools.base import ToolRegistry

_CANCEL = {"cancel", "cancel that", "cancel current task", "stop", "stop speaking"}
_TODAY = {
    "calendar today",
    "show my calendar today",
    "show me my calendar today",
    "what is on my calendar today",
    "what's on my calendar today",
}
_DAY_MISSING = {"calendar", "show my calendar", "what is on my calendar", "what's on my calendar"}


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().replace("’", "'").split())


class KeywordPlanner:
    """Implements KeywordMatcher, separate from the later async model Planner."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        apps: Mapping[str, tuple[str, ...]],
        clock: Clock,
        time_zone: tzinfo,
        confidence_threshold: float = 0.6,
    ) -> None:
        if (
            type(confidence_threshold) not in (float, int)
            or not math.isfinite(confidence_threshold)
            or not 0 <= confidence_threshold <= 1
        ):
            raise ValueError("Invalid keyword confidence threshold")
        if not isinstance(time_zone, tzinfo):
            raise TypeError("An explicit local timezone is required")
        if len(apps) > 256:
            raise ValueError("App catalog is too large")
        self._aliases: dict[str, set[str]] = {}
        for name, aliases in apps.items():
            if not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name) is None:
                raise ValueError("App IDs must be plain lowercase identifiers")
            if not isinstance(aliases, tuple) or len(aliases) > 32:
                raise ValueError("App aliases must be a bounded tuple")
            for alias in (name, *aliases):
                if not isinstance(alias, str):
                    raise TypeError("App aliases must be strings")
                if len(alias) > 80:
                    raise ValueError("App alias is too long")
                normalized = _normalize(alias)
                if (
                    len(normalized) > 80
                    or re.fullmatch(r"[a-z0-9_-]+(?: [a-z0-9_-]+)*", normalized) is None
                ):
                    raise ValueError("Invalid app alias")
                self._aliases.setdefault(normalized, set()).add(name)
        self.registry, self.clock, self.time_zone = registry, clock, time_zone
        self.confidence_threshold = confidence_threshold

    def match(self, text: str) -> KeywordResult:
        # Bound work before normalization; do not scan paragraphs for action words.
        if not isinstance(text, str) or len(text) > 512 or not text.strip():
            return KeywordResult("no_match")
        command = _normalize(text).rstrip(".?!")
        for prefix in ("could you ", "can you ", "please "):
            if command.startswith(prefix):
                command = command[len(prefix) :]
                break
        command = command.removesuffix(" please")
        if command in _CANCEL:
            return KeywordResult("cancel")
        if command in _TODAY:
            now = self.clock.now()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("The clock must return a timezone-aware datetime")
            today = now.astimezone(self.time_zone).date().isoformat()
            return self._plan("calendar_today", "cal.list", {"date": today}, 1.0)
        if command in _DAY_MISSING:
            return KeywordResult("clarify", question="Which day should I check?")
        verb, _, target = command.partition(" ")
        confidence = 1.0
        if verb not in {"open", "launch", "start"}:
            # Only the open verb can be corrected; never fuzzy-guess an app/name/date.
            if not (
                3 <= len(verb) <= 5
                and verb.isascii()
                and verb.isalpha()
                and Levenshtein.distance(verb, "open", score_cutoff=1) == 1
            ):
                return KeywordResult("no_match")
            confidence = float(Levenshtein.normalized_similarity(verb, "open"))
        candidates = self._aliases.get(target, set())
        if len(candidates) != 1:
            return KeywordResult("clarify", question="Which configured app should I open?")
        return self._plan("open_app", "apps.launch", {"name": next(iter(candidates))}, confidence)

    def _plan(
        self, intent: str, name: str, args: dict[str, Any], confidence: float
    ) -> KeywordResult:
        try:
            spec = self.registry.spec(name)
            if spec.needs_network:
                return KeywordResult("unavailable")
            candidate = Plan(
                intent=intent,
                confidence=confidence,
                risk=spec.risk,
                needs_confirmation=spec.risk != "none",
                needs_network=False,
                steps=[PlanStep(tool=name, args=args)],
            )
            review = validate_plan(
                candidate, self.registry, confidence_threshold=self.confidence_threshold
            )
        except (KeyError, PlanValidationError):
            return KeywordResult("unavailable")
        if review.requires_clarification:
            return KeywordResult("clarify", question="Could you repeat that command?")
        return KeywordResult("plan", plan=review.plan)
