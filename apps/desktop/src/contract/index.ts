/* Generated from the Pydantic contract schema. Do not edit by hand. */
import type { AgentEvent } from "./agent-events";
import type { UIEvent } from "./ui-events";
export type { AgentEvent, ActivityEntry, Citation, CloudApprovalRequest, ConfirmDetails, ConfirmRequest, ErrorEvent, OutboxItem, OutboxUpdate, PlanPreview, ReplyText, ResultAnswer, ResultDocument, SpeakerConfirmRequest, SpeakerInfo, Status, TranscriptFinal, TranscriptPartial } from "./agent-events";
export type { UIEvent, ActivityUndo, ApprovalResponse, ConfirmResponse, PttStart, PttStop, SourceOpen, SpeakerConfirmResponse, TaskCancel, TextInput, TtsStop } from "./ui-events";
export type { Plan, PlanStep } from "./plan";
export const CONTRACT_VERSION = 1 as const;
// Pydantic construction defaults are optional in raw generated types.
// Transport envelopes always include an explicit supported version and type.
export type WireAgentEvent = AgentEvent & { v: typeof CONTRACT_VERSION; type: NonNullable<AgentEvent["type"]> };
export type WireUIEvent = UIEvent & { v: typeof CONTRACT_VERSION; type: NonNullable<UIEvent["type"]> };
