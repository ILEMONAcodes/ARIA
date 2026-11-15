"""Unit tests for mail tools."""

import json

from agent.tools.mail import (
    MailAttach,
    MailDraftReply,
    MailQueueSend,
    MailReadThread,
    _FakeMailStore,
    _SimpleFakeLLM,
)


class TestMailReadThread:
    """Tests for MailReadThread tool."""

    def test_dry_run(self):
        tool = MailReadThread()
        args = tool.input_model(query="Mr Bello meeting", max_results=5)
        desc = tool.dry_run(args)
        assert "Search mail for 'Mr Bello meeting'" in desc
        assert "5" in desc

    def test_run_found_thread(self):
        fake_llm = _SimpleFakeLLM()
        fake_llm.responses = [
            json.dumps(
                {
                    "thread_id": "thread-1",
                    "subject": "Monday meeting",
                    "sender": "Mr Bello <bello@company.ng>",
                    "recipients": ["user@company.ng"],
                    "date": "2026-01-12",
                    "preview": "Please confirm our Monday 10am meeting...",
                    "message_count": 1,
                }
            )
        ]
        tool = MailReadThread(llm=fake_llm)
        args = tool.input_model(query="Mr Bello meeting", max_results=5)
        result = tool.run(args)

        assert result.threads is not None
        assert len(result.threads) == 1
        thread = result.threads[0]
        assert thread.thread_id == "thread-1"
        assert thread.subject == "Monday meeting"
        assert thread.sender == "Mr Bello <bello@company.ng>"
        assert thread.recipients == ["user@company.ng"]
        assert thread.date == "2026-01-12"
        assert thread.preview == "Please confirm our Monday 10am meeting..."
        assert thread.message_count == 1
        assert result.total == 1

    def test_run_no_thread_found(self):
        fake_llm = _SimpleFakeLLM()
        fake_llm.responses = [json.dumps({"thread_id": None, "error": "No thread found"})]
        tool = MailReadThread(llm=fake_llm)
        args = tool.input_model(query="nonexistent", max_results=5)
        result = tool.run(args)

        assert result.threads == []
        assert result.total == 0


class TestMailDraftReply:
    """Tests for MailDraftReply tool."""

    def test_dry_run(self):
        tool = MailDraftReply()
        args = tool.input_model(
            thread_id="thread-1", instruction="reply saying we will meet", tone="formal"
        )
        desc = tool.dry_run(args)
        assert "thread-1" in desc
        assert "formal" in desc

    def test_run_creates_draft(self):
        fake_llm = _SimpleFakeLLM()
        fake_llm.responses = [
            json.dumps(
                {
                    "to": ["bello@company.ng"],
                    "subject": "Re: Monday meeting",
                    "body": "Dear Mr Bello,\n\nThank you for your email. I confirm we will meet on Monday at 10am as scheduled.\n\nBest regards,",
                }
            )
        ]
        tool = MailDraftReply(llm=fake_llm, user_signature="ARIA User\nManager")
        args = tool.input_model(
            thread_id="thread-1", instruction="reply saying we will meet", tone="formal"
        )
        result = tool.run(args)

        assert result.draft_id is not None
        assert result.to == ["bello@company.ng"]
        assert result.subject == "Re: Monday meeting"
        assert "confirm we will meet on Monday at 10am" in result.body
        assert result.signature == "ARIA User\nManager"

    def test_get_draft_after_creation(self):
        fake_llm = _SimpleFakeLLM()
        fake_llm.responses = [
            json.dumps(
                {
                    "to": ["bello@company.ng"],
                    "subject": "Re: Test",
                    "body": "Test body",
                }
            )
        ]
        tool = MailDraftReply(llm=fake_llm)
        args = tool.input_model(thread_id="thread-1", instruction="test reply", tone="friendly")
        result = tool.run(args)

        draft = tool.get_draft(result.draft_id)
        assert draft is not None
        assert draft["to"] == ["bello@company.ng"]
        assert draft["subject"] == "Re: Test"
        assert draft["body"] == "Test body"

    def test_get_draft_not_found(self):
        tool = MailDraftReply()
        draft = tool.get_draft("nonexistent")
        assert draft is None


class TestMailQueueSend:
    """Tests for MailQueueSend tool."""

    def test_dry_run(self):
        tool = MailQueueSend()
        args = tool.input_model(draft_id="draft-1", confirm=True)
        desc = tool.dry_run(args)
        assert "draft-1" in desc
        assert "True" in desc

    def test_run_requires_confirmation(self):
        fake_store = _FakeMailStore()
        tool = MailQueueSend(mail_store=fake_store, draft_tool=None)
        args = tool.input_model(draft_id="draft-1", confirm=False)
        result = tool.run(args)

        assert result.outbox_id == ""
        assert result.status == "failed"
        assert "Confirmation required" in result.message

    def test_run_draft_not_found(self):
        fake_store = _FakeMailStore()
        draft_tool = MailDraftReply()
        tool = MailQueueSend(mail_store=fake_store, draft_tool=draft_tool)
        args = tool.input_model(draft_id="nonexistent", confirm=True)
        result = tool.run(args)

        assert result.outbox_id == ""
        assert result.status == "failed"
        assert "Draft not found" in result.message

    def test_run_queues_when_offline(self):
        fake_store = _FakeMailStore()
        draft_tool = MailDraftReply()
        # Pre-create a draft
        draft_tool._drafts["draft-1"] = {
            "draft_id": "draft-1",
            "thread_id": "thread-1",
            "to": ["bello@company.ng"],
            "subject": "Re: Test",
            "body": "Test body",
            "signature": "User",
            "created_at": "2026-01-01T00:00:00Z",
        }
        tool = MailQueueSend(mail_store=fake_store, draft_tool=draft_tool, network_online=False)
        args = tool.input_model(draft_id="draft-1", confirm=True)
        result = tool.run(args)

        assert result.outbox_id != ""
        assert result.status == "queued"
        assert "offline" in result.message.lower()

        # Check item was stored
        item = fake_store.get_outbox_item(result.outbox_id)
        assert item is not None
        assert item["status"] == "queued"
        assert item["idempotency_key"] == "draft-1-2026-01-01T00:00:00Z"

    def test_run_sends_when_online(self):
        fake_store = _FakeMailStore()
        draft_tool = MailDraftReply()
        draft_tool._drafts["draft-1"] = {
            "draft_id": "draft-1",
            "thread_id": "thread-1",
            "to": ["bello@company.ng"],
            "subject": "Re: Test",
            "body": "Test body",
            "signature": "User",
            "created_at": "2026-01-01T00:00:00Z",
        }
        tool = MailQueueSend(mail_store=fake_store, draft_tool=draft_tool, network_online=True)
        args = tool.input_model(draft_id="draft-1", confirm=True)
        result = tool.run(args)

        assert result.outbox_id != ""
        assert result.status == "sent"
        assert "success" in result.message.lower()

        # Check item was updated
        item = fake_store.get_outbox_item(result.outbox_id)
        assert item is not None
        assert item["status"] == "sent"

    def test_idempotency_key_format(self):
        fake_store = _FakeMailStore()
        draft_tool = MailDraftReply()
        draft_tool._drafts["draft-1"] = {
            "draft_id": "draft-1",
            "thread_id": "thread-1",
            "to": ["bello@company.ng"],
            "subject": "Re: Test",
            "body": "Test body",
            "signature": "User",
            "created_at": "2026-01-01T00:00:00Z",
        }
        tool = MailQueueSend(mail_store=fake_store, draft_tool=draft_tool, network_online=False)
        args = tool.input_model(draft_id="draft-1", confirm=True)
        result = tool.run(args)

        item = fake_store.get_outbox_item(result.outbox_id)
        assert item["idempotency_key"] == "draft-1-2026-01-01T00:00:00Z"


class TestMailAttach:
    """Tests for MailAttach tool."""

    def test_dry_run(self):
        tool = MailAttach()
        args = tool.input_model(draft_id="draft-1", description="meeting agenda")
        desc = tool.dry_run(args)
        assert "meeting agenda" in desc
        assert "draft-1" in desc

    def test_run_attaches_single_file(self):
        fake_llm = _SimpleFakeLLM()
        fake_llm.responses = [
            json.dumps(
                {
                    "attached": ["C:/Users/user/Documents/meeting_agenda.pdf"],
                    "ambiguous": [],
                    "question": None,
                }
            )
        ]
        tool = MailAttach(llm=fake_llm)
        args = tool.input_model(draft_id="draft-1", description="meeting agenda")
        result = tool.run(args)

        assert result.attached == ["C:/Users/user/Documents/meeting_agenda.pdf"]
        assert result.ambiguous == []
        assert result.question is None

    def test_run_multiple_ambiguous(self):
        fake_llm = _SimpleFakeLLM()
        fake_llm.responses = [
            json.dumps(
                {
                    "attached": [],
                    "ambiguous": [
                        "C:/Users/user/Documents/meeting_agenda_v1.pdf",
                        "C:/Users/user/Documents/meeting_agenda_v2.pdf",
                    ],
                    "question": "Which version would you like to attach?",
                }
            )
        ]
        tool = MailAttach(llm=fake_llm)
        args = tool.input_model(draft_id="draft-1", description="meeting agenda")
        result = tool.run(args)

        assert result.attached == []
        assert len(result.ambiguous) == 2
        assert result.question == "Which version would you like to attach?"

    def test_run_no_files_found(self):
        fake_llm = _SimpleFakeLLM()
        fake_llm.responses = [
            json.dumps(
                {
                    "attached": [],
                    "ambiguous": [],
                    "question": None,
                }
            )
        ]
        tool = MailAttach(llm=fake_llm)
        args = tool.input_model(draft_id="draft-1", description="nonexistent")
        result = tool.run(args)

        assert result.attached == []
        assert result.ambiguous == []
        assert result.question is None


class TestMailToolIntegration:
    """Integration tests across mail tools."""

    def test_full_flow_read_draft_send(self):
        # Read thread
        fake_llm = _SimpleFakeLLM()
        fake_llm.responses = [
            json.dumps(
                {
                    "thread_id": "thread-1",
                    "subject": "Monday meeting",
                    "sender": "Mr Bello <bello@company.ng>",
                    "recipients": ["user@company.ng"],
                    "date": "2026-01-12",
                    "preview": "Please confirm our Monday 10am meeting...",
                    "message_count": 1,
                }
            )
        ]
        read_tool = MailReadThread(llm=fake_llm)
        read_result = read_tool.run(read_tool.input_model(query="Mr Bello meeting", max_results=5))
        assert read_result.threads[0].thread_id == "thread-1"

        # Draft reply
        fake_llm.responses = [
            json.dumps(
                {
                    "to": ["bello@company.ng"],
                    "subject": "Re: Monday meeting",
                    "body": "Dear Mr Bello,\n\nThank you for your email. I confirm we will meet on Monday at 10am as scheduled.\n\nBest regards,",
                }
            )
        ]
        draft_tool = MailDraftReply(llm=fake_llm)
        draft_result = draft_tool.run(
            draft_tool.input_model(
                thread_id="thread-1", instruction="reply saying we will meet", tone="formal"
            )
        )
        assert draft_result.draft_id is not None

        # Queue send (offline)
        fake_store = _FakeMailStore()
        send_tool = MailQueueSend(
            mail_store=fake_store, draft_tool=draft_tool, network_online=False
        )
        send_result = send_tool.run(
            send_tool.input_model(draft_id=draft_result.draft_id, confirm=True)
        )
        assert send_result.status == "queued"

        # Attach file
        fake_llm.responses = [
            json.dumps(
                {
                    "attached": ["C:/Users/user/Documents/meeting_agenda.pdf"],
                    "ambiguous": [],
                    "question": None,
                }
            )
        ]
        attach_tool = MailAttach(llm=fake_llm)
        attach_result = attach_tool.run(
            attach_tool.input_model(draft_id=draft_result.draft_id, description="meeting agenda")
        )
        assert attach_result.attached == ["C:/Users/user/Documents/meeting_agenda.pdf"]


class TestFakeLLM:
    """Tests for the fake LLM adapter."""

    def test_returns_preset_responses(self):
        fake_llm = _SimpleFakeLLM()
        fake_llm.responses = ["response1", "response2"]
        assert fake_llm.complete("prompt") == "response1"
        assert fake_llm.complete("prompt") == "response2"
        assert fake_llm.complete("prompt") == "{}"  # default

    def test_default_responses(self):
        fake_llm = _SimpleFakeLLM()
        resp = fake_llm.complete("read_thread find email")
        data = json.loads(resp)
        assert data["thread_id"] == "thread-1"
        assert "Monday meeting" in data["subject"]


class TestFakeMailStore:
    """Tests for the fake mail store."""

    def test_queue_and_get(self):
        store = _FakeMailStore()
        outbox_id = store.queue_send("draft-1", ["to@test.com"], "Subject", "Body", "key-1")
        item = store.get_outbox_item(outbox_id)
        assert item is not None
        assert item["draft_id"] == "draft-1"
        assert item["to"] == ["to@test.com"]
        assert item["status"] == "queued"

    def test_update_status(self):
        store = _FakeMailStore()
        outbox_id = store.queue_send("draft-1", ["to@test.com"], "Subject", "Body", "key-1")
        store.update_status(outbox_id, "sending", attempts=1)
        item = store.get_outbox_item(outbox_id)
        assert item["status"] == "sending"
        assert item["attempts"] == 1

    def test_update_error(self):
        store = _FakeMailStore()
        outbox_id = store.queue_send("draft-1", ["to@test.com"], "Subject", "Body", "key-1")
        store.update_status(outbox_id, "failed", attempts=3, error="Network timeout")
        item = store.get_outbox_item(outbox_id)
        assert item["status"] == "failed"
        assert item["attempts"] == 3
        assert item["error"] == "Network timeout"

    def test_get_nonexistent(self):
        store = _FakeMailStore()
        item = store.get_outbox_item("nonexistent")
        assert item is None
