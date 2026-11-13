/* Generated from the Pydantic contract schema. Do not edit by hand. */

export type AgentEvent =
  | Status
  | TranscriptPartial
  | TranscriptFinal
  | SpeakerConfirmRequest
  | PlanPreview
  | CloudApprovalRequest
  | ConfirmRequest
  | ReplyText
  | ResultAnswer
  | ResultDocument
  | OutboxUpdate
  | ActivityEntry
  | ErrorEvent;
export type Online = boolean;
export type Profile = "hosted" | "local";
export type State = "idle" | "listening" | "thinking" | "working";
export type Type = "status";
export type V = number;
export type Text = string;
export type Type1 = "transcript.partial";
export type V1 = number;
export type Confidence = number;
export type Id = string;
export type Name = string;
export type Text1 = string;
export type Type2 = "transcript.final";
export type V2 = number;
export type Name1 = string;
export type Type3 = "speaker.confirm_request";
export type V3 = number;
export type Summary = string;
export type TaskId = string;
export type Type4 = "plan.preview";
export type V4 = number;
export type ApprovalId = string;
export type PayloadPreview = string;
export type Type5 = "cloud.approval_request";
export type V5 = number;
export type ConfirmId = string;
export type Attachments = string[];
export type Recipients = string[];
export type Subject = string | null;
export type DryRunText = string;
export type NeedsClick = boolean;
export type Risk = "local_write" | "external_send" | "destructive";
export type TaskId1 = string;
export type Type6 = "confirm.request";
export type V6 = number;
export type Spoken = boolean;
export type TaskId2 = string;
export type Text2 = string;
export type Type7 = "reply.text";
export type V7 = number;
export type Date = string | null;
export type Doc = string;
export type FilePath = string;
export type Page = number | null;
export type Passage = string;
export type Citations = Citation[];
export type Text3 = string;
export type Type8 = "result.answer";
export type V8 = number;
export type Path = string;
export type Title = string;
export type Type9 = "result.document";
export type V9 = number;
export type Attempts = number;
export type Id1 = string;
export type Status1 = "queued" | "sending" | "sent" | "retrying" | "failed";
export type Subject1 = string;
export type To = string[];
export type Items = OutboxItem[];
export type Type10 = "outbox.update";
export type V10 = number;
export type Id2 = string;
export type Text4 = string;
export type Ts = string;
export type Type11 = "activity.entry";
export type Undoable = boolean;
export type V11 = number;
export type Code = string;
export type Message = string;
export type Type12 = "error";
export type V12 = number;

export interface Status {
  online: Online;
  profile: Profile;
  state: State;
  type?: Type;
  v?: V;
  [k: string]: unknown;
}
export interface TranscriptPartial {
  text: Text;
  type?: Type1;
  v?: V1;
  [k: string]: unknown;
}
export interface TranscriptFinal {
  speaker?: SpeakerInfo | null;
  text: Text1;
  type?: Type2;
  v?: V2;
  [k: string]: unknown;
}
export interface SpeakerInfo {
  confidence: Confidence;
  id: Id;
  name: Name;
  [k: string]: unknown;
}
export interface SpeakerConfirmRequest {
  name: Name1;
  type?: Type3;
  v?: V3;
  [k: string]: unknown;
}
export interface PlanPreview {
  summary: Summary;
  task_id: TaskId;
  type?: Type4;
  v?: V4;
  [k: string]: unknown;
}
export interface CloudApprovalRequest {
  approval_id: ApprovalId;
  payload_preview: PayloadPreview;
  type?: Type5;
  v?: V5;
  [k: string]: unknown;
}
export interface ConfirmRequest {
  confirm_id: ConfirmId;
  details?: ConfirmDetails;
  dry_run_text: DryRunText;
  needs_click?: NeedsClick;
  risk: Risk;
  task_id: TaskId1;
  type?: Type6;
  v?: V6;
  [k: string]: unknown;
}
export interface ConfirmDetails {
  attachments?: Attachments;
  recipients?: Recipients;
  subject?: Subject;
  [k: string]: unknown;
}
export interface ReplyText {
  spoken?: Spoken;
  task_id: TaskId2;
  text: Text2;
  type?: Type7;
  v?: V7;
  [k: string]: unknown;
}
export interface ResultAnswer {
  citations?: Citations;
  text: Text3;
  type?: Type8;
  v?: V8;
  [k: string]: unknown;
}
export interface Citation {
  date?: Date;
  doc: Doc;
  file_path: FilePath;
  page?: Page;
  passage: Passage;
  [k: string]: unknown;
}
export interface ResultDocument {
  path: Path;
  title: Title;
  type?: Type9;
  v?: V9;
  [k: string]: unknown;
}
export interface OutboxUpdate {
  items: Items;
  type?: Type10;
  v?: V10;
  [k: string]: unknown;
}
export interface OutboxItem {
  attempts?: Attempts;
  id: Id1;
  status: Status1;
  subject: Subject1;
  to: To;
  [k: string]: unknown;
}
export interface ActivityEntry {
  id: Id2;
  text: Text4;
  ts: Ts;
  type?: Type11;
  undoable?: Undoable;
  v?: V11;
  [k: string]: unknown;
}
export interface ErrorEvent {
  code: Code;
  message: Message;
  type?: Type12;
  v?: V12;
  [k: string]: unknown;
}
