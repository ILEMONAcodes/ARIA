import { CONTRACT_VERSION } from "../../apps/desktop/src/contract";
import type { WireAgentEvent, WireUIEvent, Plan } from "../../apps/desktop/src/contract";

// Narrow the generated union the same way a frontend event reducer will.
export function caption(event: WireAgentEvent): string | null {
  if (event.type === "reply.text") return event.text;
  if (event.type === "result.answer") return (event.citations ?? []).map(item => item.doc).join(", ");
  if (event.type === "status") return `${event.state}: ${event.profile}`;
  return null;
}

export const confirmation: WireUIEvent = {
  v: CONTRACT_VERSION, type: "confirm.response", confirm_id: "fixture", decision: "yes", via: "click",
};
export const plan: Plan = { intent: "fixture", confidence: 0.8, steps: [] };

// @ts-expect-error On-screen confirmation must specify click or key.
export const missingInputMethod: WireUIEvent = { v: 1, type: "confirm.response", confirm_id: "fixture", decision: "yes" };
// @ts-expect-error A voice-only approval is not part of this contract.
export const voiceApproval: WireUIEvent = { v: 1, type: "confirm.response", confirm_id: "fixture", decision: "yes", via: "voice" };
// @ts-expect-error The transport version must match the generated contract.
export const wrongVersion: WireUIEvent = { v: 2, type: "ptt.start" };
// @ts-expect-error The transport envelope must contain the event discriminator.
export const missingType: WireUIEvent = { v: 1 };
