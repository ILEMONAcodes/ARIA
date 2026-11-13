/* Generated from the Pydantic contract schema. Do not edit by hand. */

export type UIEvent =
  | PttStart
  | PttStop
  | TextInput
  | ConfirmResponse
  | ApprovalResponse
  | SpeakerConfirmResponse
  | TaskCancel
  | TtsStop
  | ActivityUndo
  | SourceOpen;
export type Type = "ptt.start";
export type V = number;
export type Type1 = "ptt.stop";
export type V1 = number;
export type Text = string;
export type Type2 = "text.input";
export type V2 = number;
export type ConfirmId = string;
export type Decision = "yes" | "no";
export type Type3 = "confirm.response";
export type V3 = number;
export type Via = "click" | "key";
export type ApprovalId = string;
export type Decision1 = "yes" | "no";
export type Type4 = "approval.response";
export type V4 = number;
export type Accept = boolean;
export type Type5 = "speaker.confirm_response";
export type V5 = number;
export type TaskId = string;
export type Type6 = "task.cancel";
export type V6 = number;
export type Type7 = "tts.stop";
export type V7 = number;
export type Id = string;
export type Type8 = "activity.undo";
export type V8 = number;
export type FilePath = string;
export type Page = number | null;
export type Type9 = "source.open";
export type V9 = number;

export interface PttStart {
  type?: Type;
  v?: V;
  [k: string]: unknown;
}
export interface PttStop {
  type?: Type1;
  v?: V1;
  [k: string]: unknown;
}
export interface TextInput {
  text: Text;
  type?: Type2;
  v?: V2;
  [k: string]: unknown;
}
export interface ConfirmResponse {
  confirm_id: ConfirmId;
  decision: Decision;
  type?: Type3;
  v?: V3;
  via: Via;
  [k: string]: unknown;
}
export interface ApprovalResponse {
  approval_id: ApprovalId;
  decision: Decision1;
  type?: Type4;
  v?: V4;
  [k: string]: unknown;
}
export interface SpeakerConfirmResponse {
  accept: Accept;
  type?: Type5;
  v?: V5;
  [k: string]: unknown;
}
export interface TaskCancel {
  task_id: TaskId;
  type?: Type6;
  v?: V6;
  [k: string]: unknown;
}
export interface TtsStop {
  type?: Type7;
  v?: V7;
  [k: string]: unknown;
}
export interface ActivityUndo {
  id: Id;
  type?: Type8;
  v?: V8;
  [k: string]: unknown;
}
export interface SourceOpen {
  file_path: FilePath;
  page?: Page;
  type?: Type9;
  v?: V9;
  [k: string]: unknown;
}
