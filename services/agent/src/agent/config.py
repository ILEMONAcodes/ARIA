"""Validated agent settings. Loading configuration performs no network or storage writes."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    ValidationError,
    field_validator,
)

ENV_FIELDS = {
    "ARIA_GATEWAY_URL": "gateway_url",
    "ARIA_INSTALL_TOKEN": "install_token",
    "ARIA_PROFILE": "profile",
    "ARIA_CLOUD_ENABLED": "cloud_enabled",
    "ARIA_LIBRARY_PATH": "library_path",
    "ARIA_DB_PATH": "db_path",
    "ARIA_DB_KEY_SOURCE": "db_key_source",
    "ARIA_VAD_SILENCE_MS": "vad_silence_ms",
    "ARIA_CLOUD_TIMEOUT_S": "cloud_timeout_s",
    "ARIA_CONFIDENCE_THRESHOLD": "confidence_threshold",
    "ARIA_LOG_LEVEL": "log_level",
}


class SettingsError(ValueError):
    """Configuration error that names fields without including supplied values."""


class Settings(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, hide_input_in_errors=True, allow_inf_nan=False
    )

    gateway_url: HttpUrl | None = None
    install_token: SecretStr | None = Field(default=None, exclude=True, repr=False)
    profile: Literal["hosted", "local"] = "hosted"
    cloud_enabled: bool = True
    library_path: Path = Path("library")
    db_path: Path = Path("aria.db")
    db_key_source: Literal["os_vault"] = "os_vault"
    vad_silence_ms: int = Field(default=700, ge=500, le=800)
    cloud_timeout_s: float = Field(default=8, gt=0, le=8)
    confidence_threshold: float = Field(default=0.6, ge=0, le=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("gateway_url")
    @classmethod
    def validate_gateway_url(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None and (
            value.scheme != "https"
            or value.username is not None
            or value.password is not None
            or value.query is not None
            or value.fragment is not None
        ):
            raise ValueError("Gateway URL must use HTTPS without credentials, query or fragment")
        return value

    @field_validator("install_token", mode="before")
    @classmethod
    def normalize_token(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value


def load_settings(
    settings_file: Path | None = None, *, environ: Mapping[str, str] | None = None
) -> Settings:
    """Load defaults, then a TOML [agent] table, then known ARIA_* variables.

    File paths resolve relative to the settings file. Environment/default paths
    resolve relative to the current directory. An explicitly supplied file must
    exist and parse successfully. Tokens are accepted only from the environment.
    """
    environment = os.environ if environ is None else environ
    values: dict[str, Any] = {}
    file_directory = Path.cwd()
    if settings_file is not None:
        try:
            with settings_file.open("rb") as source:
                document = tomllib.load(source)
        except (OSError, ValueError):
            raise SettingsError("Could not read the settings file as valid TOML") from None
        if set(document) != {"agent"} or not isinstance(document["agent"], dict):
            raise SettingsError("Settings file must contain only an [agent] table")
        values = document["agent"].copy()
        if "install_token" in values:
            raise SettingsError("ARIA_INSTALL_TOKEN must be supplied through the environment")
        unknown = set(values) - (set(ENV_FIELDS.values()) - {"install_token"})
        if unknown:
            raise SettingsError("Unknown fields in the [agent] settings table")
        file_directory = settings_file.resolve().parent

    file_paths = {name for name in ("library_path", "db_path") if name in values}
    for variable, field in ENV_FIELDS.items():
        if variable in environment:
            values[field] = environment[variable]
            file_paths.discard(field)
    try:
        settings = Settings.model_validate(values)
    except ValidationError as exc:
        names = {str(error["loc"][0]) for error in exc.errors(include_input=False)}
        variables = sorted(key for key, field in ENV_FIELDS.items() if field in names)
        raise SettingsError(f"Invalid settings: {', '.join(variables)}") from None

    # Validate paths before normalizing; model_copy only receives validated Paths.
    paths = {}
    for field in ("library_path", "db_path"):
        base = file_directory if field in file_paths else Path.cwd()
        paths[field] = base / getattr(settings, field)
    return settings.model_copy(update=paths)
