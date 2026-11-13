from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes"}


@dataclass
class Settings:
    install_tokens: set[str] = field(default_factory=set)
    model: str = "gemma-4-26b-a4b"
    rate_limit_per_min: int = 30
    daily_cap_usd_per_user: float = 1.0
    fake_llm: bool = False
    # Price per million tokens (USD). Check the provider's current rates and set in config.
    input_price_per_m: float = 0.13
    output_price_per_m: float = 0.40

    @classmethod
    def from_env(cls) -> Settings:
        tokens = {
            t.strip() for t in os.environ.get("GATEWAY_INSTALL_TOKENS", "").split(",") if t.strip()
        }
        return cls(
            install_tokens=tokens,
            model=os.environ.get("GATEWAY_MODEL", "gemma-4-26b-a4b"),
            rate_limit_per_min=int(os.environ.get("GATEWAY_RATE_LIMIT_PER_MIN", "30")),
            daily_cap_usd_per_user=float(os.environ.get("GATEWAY_DAILY_CAP_USD_PER_USER", "1.0")),
            fake_llm=_bool("GATEWAY_FAKE_LLM"),
            input_price_per_m=float(os.environ.get("GATEWAY_INPUT_PRICE_PER_M", "0.13")),
            output_price_per_m=float(os.environ.get("GATEWAY_OUTPUT_PRICE_PER_M", "0.40")),
        )
