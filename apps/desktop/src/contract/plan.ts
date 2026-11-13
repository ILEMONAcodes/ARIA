/* Generated from the Pydantic contract schema. Do not edit by hand. */

export type Confidence = number;
export type Intent = string;
export type Missing = string[];
export type NeedsConfirmation = boolean;
export type NeedsNetwork = boolean;
export type Risk = "none" | "local_write" | "external_send" | "destructive";
export type Tool = string;
export type Steps = PlanStep[];

export interface Plan {
  confidence: Confidence;
  intent: Intent;
  missing?: Missing;
  needs_confirmation?: NeedsConfirmation;
  needs_network?: NeedsNetwork;
  risk?: Risk;
  slots?: Slots;
  steps?: Steps;
  [k: string]: unknown;
}
export interface Slots {
  [k: string]: unknown;
}
export interface PlanStep {
  args?: Args;
  tool: Tool;
  [k: string]: unknown;
}
export interface Args {
  [k: string]: unknown;
}
