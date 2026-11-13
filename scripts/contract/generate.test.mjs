import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { buildArtifacts, saveArtifacts } from "./generate.mjs";

test("freshness checks detect missing and stale output without rewriting it", async () => {
  const folder = await mkdtemp(join(tmpdir(), "aria-contract-"));
  try {
    const expected = new Map([["types.ts", "export type Fixture = string;\n"]]);
    await assert.rejects(saveArtifacts(expected, folder, true), /stale/);
    assert.deepEqual(await readdir(folder), []);
    await saveArtifacts(expected, folder);
    await saveArtifacts(expected, folder, true);
    const changed = new Map([["types.ts", "export type Fixture = number;\n"]]);
    await assert.rejects(saveArtifacts(changed, folder, true), /stale/);
    assert.equal(await readFile(join(folder, "types.ts"), "utf8"), expected.get("types.ts"));
  } finally { await rm(folder, { recursive: true }); }
});

test("generation refuses external references before resolving them", async () => {
  await assert.rejects(buildArtifacts({
    contract_version: 1, agent_events: { $ref: "https://example.org/private-schema" },
  }, []), /only local/);
});
