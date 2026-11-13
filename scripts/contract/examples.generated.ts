/* Generated from the Pydantic contract schema. Do not edit by hand. */
import type { WireAgentEvent, WireUIEvent } from "../../apps/desktop/src/contract";
export const agentExamples = [
  {
    "v": 1,
    "type": "transcript.final",
    "text": "Summarise this circular in five bullets.",
    "speaker": {
      "id": "u1",
      "name": "Amina",
      "confidence": 0.95
    }
  },
  {
    "v": 1,
    "type": "status",
    "state": "thinking",
    "online": true,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "error",
    "code": "cloud_unreachable",
    "message": "The cloud model did not answer. You can still use voice commands and search the policy library."
  },
  {
    "v": 1,
    "type": "reply.text",
    "task_id": "t1",
    "text": "I could not reach the cloud model. I can still open files, check your calendar and show policy passages.",
    "spoken": true
  },
  {
    "v": 1,
    "type": "status",
    "state": "idle",
    "online": false,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "status",
    "state": "listening",
    "online": true,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "transcript.final",
    "text": "Reply to Mr Bello's email and say we will meet on Monday.",
    "speaker": {
      "id": "u1",
      "name": "Amina",
      "confidence": 0.95
    }
  },
  {
    "v": 1,
    "type": "status",
    "state": "working",
    "online": true,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "cloud.approval_request",
    "approval_id": "a1",
    "payload_preview": "Thread from Mr Bello, subject: Monday meeting. Instruction: say we will meet on Monday."
  },
  {
    "v": 1,
    "type": "confirm.request",
    "confirm_id": "c1",
    "task_id": "t1",
    "risk": "external_send",
    "dry_run_text": "Send a reply to Mr Bello (bello@example.org), subject: Re: Monday meeting. Body: Thank you for your email. We will meet on Monday.",
    "details": {
      "recipients": [
        "bello@example.org"
      ],
      "subject": "Re: Monday meeting",
      "attachments": []
    },
    "needs_click": true
  },
  {
    "v": 1,
    "type": "outbox.update",
    "items": [
      {
        "id": "o1",
        "status": "sending",
        "to": [
          "bello@example.org"
        ],
        "subject": "Re: Monday meeting",
        "attempts": 1
      }
    ]
  },
  {
    "v": 1,
    "type": "outbox.update",
    "items": [
      {
        "id": "o1",
        "status": "sent",
        "to": [
          "bello@example.org"
        ],
        "subject": "Re: Monday meeting",
        "attempts": 1
      }
    ]
  },
  {
    "v": 1,
    "type": "activity.entry",
    "id": "act1",
    "ts": "2026-01-01T09:00:00Z",
    "text": "Sent a reply to Mr Bello about the Monday meeting.",
    "undoable": false
  },
  {
    "v": 1,
    "type": "reply.text",
    "task_id": "t1",
    "text": "Your reply to Mr Bello has been sent.",
    "spoken": true
  },
  {
    "v": 1,
    "type": "status",
    "state": "idle",
    "online": true,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "status",
    "state": "idle",
    "online": false,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "transcript.final",
    "text": "Send the reply.",
    "speaker": {
      "id": "u1",
      "name": "Amina",
      "confidence": 0.95
    }
  },
  {
    "v": 1,
    "type": "confirm.request",
    "confirm_id": "c1",
    "task_id": "t1",
    "risk": "external_send",
    "dry_run_text": "Send the reply to Mr Bello. The internet is off, so it will wait in the outbox.",
    "details": {
      "recipients": [
        "bello@example.org"
      ],
      "subject": "Re: Monday meeting",
      "attachments": []
    },
    "needs_click": true
  },
  {
    "v": 1,
    "type": "outbox.update",
    "items": [
      {
        "id": "o1",
        "status": "queued",
        "to": [
          "bello@example.org"
        ],
        "subject": "Re: Monday meeting",
        "attempts": 0
      }
    ]
  },
  {
    "v": 1,
    "type": "reply.text",
    "task_id": "t1",
    "text": "No internet. Your reply is queued and will send when it returns.",
    "spoken": true
  },
  {
    "v": 1,
    "type": "status",
    "state": "idle",
    "online": true,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "outbox.update",
    "items": [
      {
        "id": "o1",
        "status": "sending",
        "to": [
          "bello@example.org"
        ],
        "subject": "Re: Monday meeting",
        "attempts": 1
      }
    ]
  },
  {
    "v": 1,
    "type": "outbox.update",
    "items": [
      {
        "id": "o1",
        "status": "sent",
        "to": [
          "bello@example.org"
        ],
        "subject": "Re: Monday meeting",
        "attempts": 1
      }
    ]
  },
  {
    "v": 1,
    "type": "reply.text",
    "task_id": "t1",
    "text": "Your reply to Mr Bello has now been sent.",
    "spoken": true
  },
  {
    "v": 1,
    "type": "status",
    "state": "listening",
    "online": true,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "transcript.partial",
    "text": "What does the circular say about"
  },
  {
    "v": 1,
    "type": "transcript.final",
    "text": "What does the circular say about annual leave carry-over?",
    "speaker": {
      "id": "u1",
      "name": "Amina",
      "confidence": 0.96
    }
  },
  {
    "v": 1,
    "type": "status",
    "state": "thinking",
    "online": true,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "cloud.approval_request",
    "approval_id": "a1",
    "payload_preview": "Question: What does the circular say about annual leave carry-over? Passages: Leave Circular 2024, page 3."
  },
  {
    "v": 1,
    "type": "result.answer",
    "text": "Staff may carry over up to five unused leave days into the next year [Leave Circular 2024, page 3]. Days not used by 31 March lapse [Leave Circular 2024, page 3].",
    "citations": [
      {
        "doc": "Leave Circular 2024",
        "page": 3,
        "date": "2024-01-15",
        "passage": "Up to five unused days of annual leave may be carried over to the next calendar year. Carried-over days not used by 31 March lapse.",
        "file_path": "library/leave_circular_2024.pdf"
      }
    ]
  },
  {
    "v": 1,
    "type": "reply.text",
    "task_id": "t1",
    "text": "You can carry over up to five days. Say show me to open the circular.",
    "spoken": true
  },
  {
    "v": 1,
    "type": "status",
    "state": "idle",
    "online": true,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "status",
    "state": "idle",
    "online": false,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "status",
    "state": "listening",
    "online": false,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "status",
    "state": "thinking",
    "online": false,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "transcript.partial",
    "text": "Open the policy folder."
  },
  {
    "v": 1,
    "type": "transcript.final",
    "text": "Open the policy folder."
  },
  {
    "v": 1,
    "type": "status",
    "state": "working",
    "online": false,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "reply.text",
    "task_id": "voice-fixture",
    "text": "Open the policy folder.",
    "spoken": true
  },
  {
    "v": 1,
    "type": "status",
    "state": "listening",
    "online": false,
    "profile": "hosted"
  },
  {
    "v": 1,
    "type": "activity.entry",
    "id": "voice-activity-fixture",
    "ts": "2026-01-01T00:00:00Z",
    "text": "Voice echo completed.",
    "undoable": false
  },
  {
    "v": 1,
    "type": "status",
    "state": "idle",
    "online": false,
    "profile": "hosted"
  }
] satisfies WireAgentEvent[];
export const uiExamples = [
  {
    "v": 1,
    "type": "approval.response",
    "approval_id": "a1",
    "decision": "yes"
  },
  {
    "v": 1,
    "type": "confirm.response",
    "confirm_id": "c1",
    "decision": "yes",
    "via": "click"
  },
  {
    "v": 1,
    "type": "confirm.response",
    "confirm_id": "c1",
    "decision": "yes",
    "via": "click"
  },
  {
    "v": 1,
    "type": "approval.response",
    "approval_id": "a1",
    "decision": "yes"
  },
  {
    "v": 1,
    "type": "source.open",
    "file_path": "library/leave_circular_2024.pdf",
    "page": 3
  },
  {
    "v": 1,
    "type": "ptt.start"
  },
  {
    "v": 1,
    "type": "ptt.stop"
  }
] satisfies WireUIEvent[];
