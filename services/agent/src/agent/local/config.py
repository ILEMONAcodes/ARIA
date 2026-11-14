"""Explicit local tool paths, with no discovery, default applications or secret fields."""

from __future__ import annotations

import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from agent.kb.tool import PolicySearch
from agent.tools.apps import AppLauncher
from agent.tools.base import ToolRegistry
from agent.tools.calendar import CalendarList


class App(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executable: Path
    aliases: tuple[str, ...] = ()


class LocalTools(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str
    calendar: Path | None = None
    policy_folder: Path | None = None
    policy_database: Path | None = None
    apps: dict[str, App] = {}


def load_tools(path: Path) -> tuple[ToolRegistry, dict[str, tuple[str, ...]], ZoneInfo]:
    try:
        config = LocalTools.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
        zone = ZoneInfo(config.timezone)
        root = path.resolve().parent
        registry = ToolRegistry()
        executables = {
            name: (root / app.executable).resolve(strict=True) for name, app in config.apps.items()
        }
        if executables:
            registry.register(AppLauncher(executables))
        if config.calendar is not None:
            registry.register(
                CalendarList((root / config.calendar).resolve(strict=True), config.timezone)
            )
        if (config.policy_folder is None) != (config.policy_database is None):
            raise ValueError("Both policy paths are required")
        if config.policy_folder is not None and config.policy_database is not None:
            registry.register(
                PolicySearch(root / config.policy_folder, root / config.policy_database)
            )
        return registry, {name: app.aliases for name, app in config.apps.items()}, zone
    except (ValueError, OSError, KeyError):
        raise ValueError("Invalid local tool configuration") from None
