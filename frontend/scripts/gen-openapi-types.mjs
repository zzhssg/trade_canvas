import { spawnSync } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

import openapiTS, { COMMENT_HEADER, astToString } from "openapi-typescript";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");

async function readOpenApiSchema() {
  const script = path.join(repoRoot, "scripts/gen_openapi_json.py");
  const res = spawnSync(process.env.PYTHON ?? "python3", [script], {
    cwd: repoRoot,
    encoding: "utf-8"
  });
  if (res.status !== 0) {
    process.stderr.write(res.stderr || "");
    throw new Error(`OpenAPI schema generation failed (exit=${res.status})`);
  }
  const stdout = res.stdout || "";
  return JSON.parse(stdout);
}

async function main() {
  const schema = await readOpenApiSchema();
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "trade-canvas-openapi-"));
  const tmpSchemaPath = path.join(tmpDir, "openapi.json");
  await fs.writeFile(tmpSchemaPath, JSON.stringify(schema, null, 2), "utf-8");

  const ast = await openapiTS(pathToFileURL(tmpSchemaPath));
  const output =
    COMMENT_HEADER +
    `/**\n * Generated from FastAPI OpenAPI (repo-local generator).\n * Source: backend/app/main.py (create_app().openapi())\n */\n\n` +
    astToString(ast);

  const outPath = path.join(repoRoot, "frontend/src/contracts/openapi.ts");
  await fs.mkdir(path.dirname(outPath), { recursive: true });
  await fs.writeFile(outPath, output, "utf-8");
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
