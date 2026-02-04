import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { build } from "esbuild";

const repoRoot = path.resolve(new URL("..", import.meta.url).pathname);
const tmpDir = await mkdtemp(path.join(os.tmpdir(), "trade-canvas-test-"));

try {
  const outfile = path.join(tmpDir, "barSpacing.mjs");
  await build({
    entryPoints: [path.join(repoRoot, "src/widgets/chart/barSpacing.ts")],
    outfile,
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    sourcemap: false,
    logLevel: "silent"
  });

  const mod = await import(pathToFileURL(outfile).toString());

  assert.equal(mod.clampBarSpacing(100, 20), 20);
  assert.equal(mod.clampBarSpacing(10, 20), 10);
  assert.equal(mod.clampBarSpacing(Number.NaN, 20), 20);
  assert.equal(mod.clampBarSpacing(100, Number.NaN), 100);
  assert.equal(mod.clampBarSpacing(100, 0), 100);

  assert.equal(mod.MAX_BAR_SPACING_ON_FIT_CONTENT, 20);

  console.log("ok: barSpacing clamp");
} finally {
  await rm(tmpDir, { recursive: true, force: true });
}

