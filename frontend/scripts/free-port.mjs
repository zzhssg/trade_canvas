import { execFileSync, spawnSync } from "node:child_process";

function usage() {
  console.error("Usage: node scripts/free-port.mjs <port>");
  process.exit(2);
}

const portRaw = process.argv[2];
if (!portRaw) usage();

const port = Number(portRaw);
if (!Number.isInteger(port) || port <= 0 || port > 65535) usage();

function run(cmd, args) {
  return execFileSync(cmd, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function killPids(pids, signal) {
  for (const pid of pids) {
    try {
      process.kill(pid, signal);
    } catch {
      // ignore (process already exited / not permitted)
    }
  }
}

function isPidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function uniqueInts(values) {
  return [...new Set(values.map((v) => Number(v)).filter((n) => Number.isInteger(n) && n > 0))];
}

function pidsFromLsof() {
  const lsof = spawnSync("lsof", ["-ti", `tcp:${port}`], { encoding: "utf8" });
  if (lsof.status === 1) return []; // no matches
  if (lsof.status !== 0) {
    const err = (lsof.stderr || "").trim();
    throw new Error(err || "lsof failed");
  }
  const out = (lsof.stdout || "").trim();
  if (!out) return [];
  return uniqueInts(out.split(/\s+/));
}

function pidsFromNetstatWindows() {
  const out = run("cmd.exe", ["/c", `netstat -ano | findstr :${port}`]);
  const pids = [];
  for (const line of out.split("\n")) {
    const parts = line.trim().split(/\s+/);
    const pid = parts.at(-1);
    if (pid) pids.push(pid);
  }
  return uniqueInts(pids);
}

function main() {
  const platform = process.platform;

  let pids = [];
  if (platform === "win32") {
    try {
      pids = pidsFromNetstatWindows();
    } catch {
      pids = [];
    }
  } else {
    try {
      pids = pidsFromLsof();
    } catch (e) {
      console.error(`[free-port] Unable to find process on port ${port}: ${e instanceof Error ? e.message : String(e)}`);
      process.exit(1);
    }
  }

  if (pids.length === 0) {
    console.log(`[free-port] Port ${port} is free.`);
    return;
  }

  console.log(`[free-port] Port ${port} is in use by PID(s): ${pids.join(", ")}. Sending SIGTERM...`);
  if (platform === "win32") {
    for (const pid of pids) {
      spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "inherit" });
    }
    return;
  }

  killPids(pids, "SIGTERM");
  sleep(400);

  const stillAlive = pids.filter(isPidAlive);
  if (stillAlive.length === 0) {
    console.log(`[free-port] Freed port ${port}.`);
    return;
  }

  console.log(`[free-port] PID(s) still alive: ${stillAlive.join(", ")}. Sending SIGKILL...`);
  killPids(stillAlive, "SIGKILL");
  sleep(200);

  const finalAlive = stillAlive.filter(isPidAlive);
  if (finalAlive.length === 0) {
    console.log(`[free-port] Freed port ${port}.`);
    return;
  }

  console.error(`[free-port] Failed to kill PID(s): ${finalAlive.join(", ")} (insufficient permissions?).`);
  process.exit(1);
}

main();

