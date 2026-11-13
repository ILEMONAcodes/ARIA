from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from gateway.config import Settings
from gateway.llm import FakeLLM, LLMClient, ProviderLLM

log = logging.getLogger("gateway")


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["system", "user", "assistant"]
    content: str


class DataBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    text: str


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_tokens: int = Field(default=600, ge=1, le=4000)
    temperature: float = Field(default=0.2, ge=0, le=2)
    reasoning: bool = False
    json_schema: dict[str, Any] | None = None


class CompleteRequest(BaseModel):
    # extra="forbid" means audio fields (or anything unexpected) are rejected.
    model_config = ConfigDict(extra="forbid")
    task: Literal["answer", "summarise", "draft", "reply", "plan"]
    messages: list[Message]
    data_blocks: list[DataBlock] = []
    params: Params = Params()
    client_request_id: str | None = None


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class CompleteResponse(BaseModel):
    text: str
    usage: Usage
    model: str
    request_id: str


class State:
    """In-memory counters. Replace with Redis or a database before running more than one instance."""

    def __init__(self) -> None:
        self.calls: dict[str, list[float]] = defaultdict(list)
        self.spend_usd: dict[str, float] = defaultdict(float)


def error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    llm = llm or (FakeLLM() if settings.fake_llm else ProviderLLM())
    state = State()
    app = FastAPI(title="ARIA gateway")

    def auth(authorization: str | None = Header(default=None)) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise error(401, "unauthorized", "Missing or invalid token")
        token = authorization.removeprefix("Bearer ").strip()
        if token not in settings.install_tokens:
            raise error(401, "unauthorized", "Missing or invalid token")
        return token

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/complete", response_model=CompleteResponse)
    def complete(req: CompleteRequest, token: str = Depends(auth)) -> CompleteResponse:
        now = time.time()
        recent = [t for t in state.calls[token] if now - t < 60]
        if len(recent) >= settings.rate_limit_per_min:
            raise error(429, "rate_limited", "Too many requests")
        if state.spend_usd[token] >= settings.daily_cap_usd_per_user:
            raise error(429, "spending_cap", "Daily spending cap reached")
        recent.append(now)
        state.calls[token] = recent

        messages = [m.model_dump() for m in req.messages]
        for block in req.data_blocks:
            messages.append(
                {
                    "role": "user",
                    "content": f'<data id="{block.id}" label="{block.label}">\n{block.text}\n</data>',
                }
            )
        result = llm.complete(messages, req.params.model_dump())
        cost = (
            result.input_tokens * settings.input_price_per_m
            + result.output_tokens * settings.output_price_per_m
        ) / 1_000_000
        state.spend_usd[token] += cost
        # Log usage only. Never log request or response content.
        log.info(
            "usage task=%s in=%d out=%d cost=%.6f",
            req.task,
            result.input_tokens,
            result.output_tokens,
            cost,
        )
        return CompleteResponse(
            text=result.text,
            usage=Usage(input_tokens=result.input_tokens, output_tokens=result.output_tokens),
            model=settings.model,
            request_id=req.client_request_id or "req",
        )

    return app
