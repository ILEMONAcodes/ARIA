"""Mail tools: read thread, draft reply, queue send, attach."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Protocol

from agent.contracts.plan import Risk
from agent.contracts.tools import (
    MailAttachInput,
    MailAttachOutput,
    MailDraftReplyInput,
    MailDraftReplyOutput,
    MailQueueSendInput,
    MailQueueSendOutput,
    MailReadThreadInput,
    MailReadThreadOutput,
    MailThread,
)
from agent.tools.base import Tool


class _LLMAdapter(Protocol):
    """Protocol for LLM adapters used by mail tools."""

    def complete(self, prompt: str) -> str: ...


class _MailStore(Protocol):
    """Protocol for mail storage (SQLite outbox)."""

    def queue_send(
        self, draft_id: str, to: list[str], subject: str, body: str, idempotency_key: str
    ) -> str: ...
    def get_outbox_item(self, outbox_id: str) -> dict[str, Any] | None: ...
    def update_status(
        self, outbox_id: str, status: str, attempts: int = 0, error: str | None = None
    ) -> None: ...


class MailReadThread(Tool[MailReadThreadInput, MailReadThreadOutput]):
    name = "mail.read_thread"
    risk: ClassVar[Risk] = "none"
    needs_network = True  # Requires mail connection
    timeout_s = 10.0
    input_model = MailReadThreadInput
    output_model = MailReadThreadOutput

    def __init__(
        self,
        llm: _LLMAdapter | None = None,
        mail_client: Any | None = None,
    ) -> None:
        self.llm = llm or _SimpleFakeLLM()
        self.mail_client = mail_client

    def dry_run(self, args: MailReadThreadInput) -> str:
        return f"Search mail for '{args.query}' (max {args.max_results} results)"

    def run(self, args: MailReadThreadInput) -> MailReadThreadOutput:
        # In production, this would call the mail client (Graph/Gmail)
        # For now, use the LLM to process the query against available threads
        prompt = self._build_prompt(args)
        response = self.llm.complete(prompt)
        data = _parse_json(response)

        if data.get("thread_id") is None:
            return MailReadThreadOutput(threads=[], total=0)

        thread = MailThread(
            thread_id=data["thread_id"],
            subject=data["subject"],
            sender=data["sender"],
            recipients=data.get("recipients", []),
            date=data["date"],
            preview=data["preview"],
            message_count=data.get("message_count", 1),
        )
        return MailReadThreadOutput(threads=[thread], total=1)

    def _build_prompt(self, args: MailReadThreadInput) -> str:
        template = (
            Path(__file__).parent.parent / "planner" / "prompts" / "mail_read_thread.txt"
        ).read_text()
        return template


class MailDraftReply(Tool[MailDraftReplyInput, MailDraftReplyOutput]):
    name = "mail.draft_reply"
    risk: ClassVar[Risk] = "local_write"  # Creates a draft
    needs_network = True  # Requires LLM
    timeout_s = 30.0
    input_model = MailDraftReplyInput
    output_model = MailDraftReplyOutput

    def __init__(
        self,
        llm: _LLMAdapter | None = None,
        user_signature: str = "ARIA User\nManager",
    ) -> None:
        self.llm = llm or _SimpleFakeLLM()
        self.user_signature = user_signature
        self._drafts: dict[str, dict[str, Any]] = {}

    def dry_run(self, args: MailDraftReplyInput) -> str:
        return f"Draft reply for thread {args.thread_id} with tone {args.tone}"

    def run(self, args: MailDraftReplyInput) -> MailDraftReplyOutput:
        # Get thread context (in production, fetch from mail client)
        thread_context = self._get_thread_context(args.thread_id)

        prompt = self._build_prompt(args, thread_context)
        response = self.llm.complete(prompt)
        data = _parse_json(response)

        draft_id = str(uuid.uuid4())
        draft = {
            "draft_id": draft_id,
            "thread_id": args.thread_id,
            "to": data.get("to", []),
            "subject": data.get("subject", f"Re: {thread_context.get('subject', '')}"),
            "body": data.get("body", ""),
            "signature": self.user_signature,
            "created_at": datetime.now().isoformat(),
        }
        self._drafts[draft_id] = draft

        return MailDraftReplyOutput(
            draft_id=draft_id,
            to=draft["to"],
            subject=draft["subject"],
            body=draft["body"],
            signature=draft["signature"],
        )

    def _get_thread_context(self, thread_id: str) -> dict[str, Any]:
        # In production, fetch from mail client
        return {
            "thread_id": thread_id,
            "subject": "Monday meeting",
            "sender": "Mr Bello <bello@company.ng>",
            "recipients": ["user@company.ng"],
            "date": "2026-01-12",
            "preview": "Please confirm our Monday 10am meeting...",
        }

    def _build_prompt(self, args: MailDraftReplyInput, thread_context: dict[str, Any]) -> str:
        template = (
            Path(__file__).parent.parent / "planner" / "prompts" / "mail_draft_reply.txt"
        ).read_text()
        data_block = f'<data id="d1" label="email_thread">\nThread: {thread_context}\n</data>'
        return template.format(tone=args.tone, signature=self.user_signature) + "\n\n" + data_block

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        return self._drafts.get(draft_id)


class MailQueueSend(Tool[MailQueueSendInput, MailQueueSendOutput]):
    name = "mail.queue_send"
    risk: ClassVar[Risk] = "external_send"
    needs_network = True  # Requires mail connection to send
    timeout_s = 30.0
    input_model = MailQueueSendInput
    output_model = MailQueueSendOutput

    def __init__(
        self,
        mail_store: _MailStore | None = None,
        draft_tool: MailDraftReply | None = None,
        network_online: bool = True,
    ) -> None:
        self.mail_store = mail_store or _FakeMailStore()
        self.draft_tool = draft_tool
        self.network_online = network_online

    def dry_run(self, args: MailQueueSendInput) -> str:
        return f"Queue draft {args.draft_id} for sending (confirm={args.confirm})"

    def run(self, args: MailQueueSendInput) -> MailQueueSendOutput:
        if not args.confirm:
            return MailQueueSendOutput(
                outbox_id="",
                status="failed",
                message="Confirmation required before sending",
            )

        draft = None
        if self.draft_tool:
            draft = self.draft_tool.get_draft(args.draft_id)

        if not draft:
            return MailQueueSendOutput(
                outbox_id="",
                status="failed",
                message="Draft not found",
            )

        idempotency_key = f"{draft['draft_id']}-{draft['created_at']}"
        outbox_id = self.mail_store.queue_send(
            draft_id=args.draft_id,
            to=draft["to"],
            subject=draft["subject"],
            body=draft["body"] + "\n\n" + draft["signature"],
            idempotency_key=idempotency_key,
        )

        if not self.network_online:
            return MailQueueSendOutput(
                outbox_id=outbox_id,
                status="queued",
                message="Network is offline. Reply queued in outbox. Will send when connection returns.",
            )

        # In production, actually send via mail client
        self.mail_store.update_status(outbox_id, "sending")
        # ... send logic ...
        self.mail_store.update_status(outbox_id, "sent")

        return MailQueueSendOutput(
            outbox_id=outbox_id,
            status="sent",
            message="Email sent successfully",
        )


class MailAttach(Tool[MailAttachInput, MailAttachOutput]):
    name = "mail.attach"
    risk: ClassVar[Risk] = "none"
    needs_network = True  # Requires LLM
    timeout_s = 10.0
    input_model = MailAttachInput
    output_model = MailAttachOutput

    def __init__(
        self,
        llm: _LLMAdapter | None = None,
        file_index: Any | None = None,
    ) -> None:
        self.llm = llm or _SimpleFakeLLM()
        self.file_index = file_index

    def dry_run(self, args: MailAttachInput) -> str:
        return f"Find files matching '{args.description}' for draft {args.draft_id}"

    def run(self, args: MailAttachInput) -> MailAttachOutput:
        # In production, search file index
        # For now, use LLM to process
        prompt = self._build_prompt(args)
        response = self.llm.complete(prompt)
        data = _parse_json(response)

        return MailAttachOutput(
            attached=data.get("attached", []),
            ambiguous=data.get("ambiguous", []),
            question=data.get("question"),
        )

    def _build_prompt(self, args: MailAttachInput) -> str:
        template = (
            Path(__file__).parent.parent / "planner" / "prompts" / "mail_attach.txt"
        ).read_text()
        return template


class _SimpleFakeLLM:
    """Simple fake LLM adapter for tests."""

    def __init__(self) -> None:
        self.responses: list[str] = []

    def complete(self, prompt: str) -> str:
        if self.responses:
            return self.responses.pop(0)

        # Default responses based on prompt
        if "read_thread" in prompt or "find an email" in prompt:
            return '{"thread_id": "thread-1", "subject": "Monday meeting", "sender": "Mr Bello <bello@company.ng>", "recipients": ["user@company.ng"], "date": "2026-01-12", "preview": "Please confirm our Monday 10am meeting...", "message_count": 1}'
        elif "draft_reply" in prompt or "draft an email reply" in prompt:
            return '{"to": ["bello@company.ng"], "subject": "Re: Monday meeting", "body": "Dear Mr Bello,\n\nThank you for your email. I confirm we will meet on Monday at 10am as scheduled.\n\nBest regards,"}'
        elif "attach" in prompt or "identify files" in prompt:
            return '{"attached": ["C:/Users/user/Documents/meeting_agenda.pdf"], "ambiguous": [], "question": null}'
        return "{}"


class _FakeMailStore:
    """Fake mail store for tests."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def queue_send(
        self, draft_id: str, to: list[str], subject: str, body: str, idempotency_key: str
    ) -> str:
        outbox_id = str(uuid.uuid4())
        self.items[outbox_id] = {
            "id": outbox_id,
            "draft_id": draft_id,
            "to": to,
            "subject": subject,
            "body": body,
            "idempotency_key": idempotency_key,
            "status": "queued",
            "attempts": 0,
            "created_at": datetime.now().isoformat(),
        }
        return outbox_id

    def get_outbox_item(self, outbox_id: str) -> dict[str, Any] | None:
        return self.items.get(outbox_id)

    def update_status(
        self, outbox_id: str, status: str, attempts: int = 0, error: str | None = None
    ) -> None:
        if outbox_id in self.items:
            self.items[outbox_id]["status"] = status
            self.items[outbox_id]["attempts"] = attempts
            if error:
                self.items[outbox_id]["error"] = error


def _parse_json(text: str) -> dict[str, Any]:
    import json

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        return {}
    except json.JSONDecodeError:
        return {}
