import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const directory = dirname(fileURLToPath(import.meta.url));
for (const args of [
  ["--test", "generate.test.mjs"],
  ["generate.mjs", "--check"],
  [resolve(directory, "node_modules/typescript/bin/tsc"), "--project", "tsconfig.json"],
]) {
  const result = spawnSync(process.execPath, args, { cwd: directory, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
