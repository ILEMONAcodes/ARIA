import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readdir } from "node:fs/promises";
import { compile } from "json-schema-to-typescript";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const banner = "/* Generated from the Pydantic contract schema. Do not edit by hand. */";

function localReferencesOnly(value) {
  if (value === null || typeof value !== "object") return;
  if ("$ref" in value && (typeof value.$ref !== "string" || !value.$ref.startsWith("#/"))) {
    throw new Error("Contract generation permits only local JSON references");
  }
  for (const child of Object.values(value)) localReferencesOnly(child);
}

export async function buildArtifacts(schema, scenarios) {
  if (!Number.isSafeInteger(schema.contract_version) || schema.contract_version < 1) {
    throw new Error("Invalid contract version");
  }
  localReferencesOnly(schema);
  const artifacts = new Map();
  for (const [key, name, filename] of [
    ["agent_events", "AgentEvent", "agent-events.ts"],
    ["ui_events", "UIEvent", "ui-events.ts"],
    ["plan", "Plan", "plan.ts"],
  ]) {
    artifacts.set(`apps/desktop/src/contract/${filename}`, await compile(schema[key], name, {
      bannerComment: banner,
      unknownAny: true,
      $refOptions: { resolve: { file: false, http: false } },
      style: { endOfLine: "lf" },
    }));
  }
  artifacts.set("apps/desktop/src/contract/index.ts", `${banner}
import type { AgentEvent } from "./agent-events";
import type { UIEvent } from "./ui-events";
export type { AgentEvent, ${Object.keys(schema.agent_events.$defs).join(", ")} } from "./agent-events";
export type { UIEvent, ${Object.keys(schema.ui_events.$defs).join(", ")} } from "./ui-events";
export type { Plan, ${Object.keys(schema.plan.$defs).join(", ")} } from "./plan";
export const CONTRACT_VERSION = ${schema.contract_version} as const;
// Pydantic construction defaults are optional in raw generated types.
// Transport envelopes always include an explicit supported version and type.
export type WireAgentEvent = AgentEvent & { v: typeof CONTRACT_VERSION; type: NonNullable<AgentEvent["type"]> };
export type WireUIEvent = UIEvent & { v: typeof CONTRACT_VERSION; type: NonNullable<UIEvent["type"]> };
`);
  const agent = scenarios.flatMap(s => s.steps.filter(step => "send" in step).map(step => step.send));
  const ui = scenarios.flatMap(s => s.steps.filter(step => step.match).map(step => step.match));
  artifacts.set("scripts/contract/examples.generated.ts", `${banner}
import type { WireAgentEvent, WireUIEvent } from "../../apps/desktop/src/contract";
export const agentExamples = ${JSON.stringify(agent, null, 2)} satisfies WireAgentEvent[];
export const uiExamples = ${JSON.stringify(ui, null, 2)} satisfies WireUIEvent[];
`);
  return artifacts;
}

export async function saveArtifacts(artifacts, destination, check = false) {
  // Check everything before writing; --check never creates or rewrites a file.
  const stale = [];
  for (const [filename, expected] of artifacts) {
    const current = await readFile(resolve(destination, filename), "utf8").catch(error => {
      if (error.code === "ENOENT") return null;
      throw error;
    });
    if (current !== expected) stale.push(filename);
  }
  if (check) {
    if (stale.length) throw new Error(`Generated contract files are stale: ${stale.join(", ")}`);
    return;
  }
  for (const filename of stale) {
    const target = resolve(destination, filename);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, artifacts.get(filename), "utf8");
  }
}

async function main() {
  if (process.argv.slice(2).some(arg => arg !== "--check")) throw new Error("Usage: node generate.mjs [--check]");
  const schema = JSON.parse(await readFile(resolve(root, "apps/desktop/src/contract/schema.json"), "utf8"));
  const folder = resolve(root, "tests/e2e/scenarios");
  const filenames = (await readdir(folder)).filter(name => name.endsWith(".json")).sort();
  const scenarios = await Promise.all(filenames.map(async name => JSON.parse(await readFile(resolve(folder, name), "utf8"))));
  await saveArtifacts(await buildArtifacts(schema, scenarios), root, process.argv.includes("--check"));
  console.log(process.argv.includes("--check") ? "Contract types and examples are up to date" : "Generated contract types and examples");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
