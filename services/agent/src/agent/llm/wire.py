"""Strict gateway request/response values, separate from the desktop v1 contract."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent.interfaces.models import DataBlock, ModelMessage, ModelRequest


class WireModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, allow_inf_nan=False, hide_input_in_errors=True
    )


class Message(WireModel):
    role: Literal["system", "user", "assistant"]
    content: str


class Block(WireModel):
    id: str
    label: str
    text: str


class Params(WireModel):
    max_tokens: int = Field(ge=1, le=4000)
    temperature: float = Field(ge=0, le=2)
    reasoning: bool
    json_schema: dict[str, Any] | None


class Body(WireModel):
    task: Literal["answer", "summarise", "draft", "reply", "plan"]
    messages: list[Message] = Field(min_length=1)
    data_blocks: list[Block]
    params: Params
    client_request_id: str


class Usage(WireModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class Response(WireModel):
    text: str = Field(min_length=1)
    usage: Usage
    model: str = Field(min_length=1)
    request_id: str


def data_rule() -> str:
    return (
        files("agent.planner.prompts").joinpath("data_rule.txt").read_text(encoding="utf-8").strip()
    )


def encode_request(request: ModelRequest) -> bytes:
    messages = [Message(role=m.role, content=m.content) for m in request.messages]
    if request.data_blocks:
        rule = data_rule()
        if not any(m.role == "system" and rule in m.content for m in messages):
            messages.insert(0, Message(role="system", content=rule))
    identifier = str(UUID(request.client_request_id)) if request.client_request_id else str(uuid4())
    body = Body(
        task=request.task,
        messages=messages,
        data_blocks=[Block(id=b.id, label=b.label, text=b.text) for b in request.data_blocks],
        params=Params(
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            reasoning=request.reasoning,
            json_schema=request.json_schema,
        ),
        client_request_id=identifier,
    )
    value = json.dumps(
        body.model_dump(), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    ).encode("utf-8")
    if len(value) > 65536:
        raise ValueError("Gateway request exceeds the preview limit")
    return value


def snapshot(request: ModelRequest) -> tuple[ModelRequest, str]:
    """Round-trip into privately owned values; approval and retries use the same bytes."""
    value = encode_request(request)
    body = Body.model_validate_json(value)
    frozen = ModelRequest(
        task=body.task,
        messages=tuple(ModelMessage(m.role, m.content) for m in body.messages),
        data_blocks=tuple(DataBlock(b.id, b.label, b.text) for b in body.data_blocks),
        max_tokens=body.params.max_tokens,
        temperature=body.params.temperature,
        reasoning=body.params.reasoning,
        json_schema=body.params.json_schema,
        client_request_id=body.client_request_id,
    )
    return frozen, value.decode("utf-8")
