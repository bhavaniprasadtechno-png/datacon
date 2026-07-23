#!/usr/bin/env node
// Boots the FastAPI AI service by invoking its venv's own uvicorn binary
// directly (no "activate" step, no shell). This avoids relying on a `bash`
// on PATH, which on Windows can resolve to the WSL launcher
// (C:\Windows\System32\bash.exe) instead of Git Bash depending on which
// shell/terminal npm was invoked from.
const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");

const aiDir = path.join(__dirname, "..", "ai");
require("dotenv").config({ path: path.join(aiDir, ".env") });
const port = process.env.AI_DEV_PORT || "8000";

const winVenvUvicorn = path.join(aiDir, ".venv", "Scripts", "uvicorn.exe");
const wslVenvUvicorn = path.join(aiDir, ".venv", "bin", "uvicorn");

let child;

if (process.platform === "win32" && fs.existsSync(winVenvUvicorn)) {
  child = spawn(winVenvUvicorn, ["app.main:app", "--reload", "--port", port], {
    cwd: aiDir,
    stdio: "inherit",
  });
} else if (fs.existsSync(wslVenvUvicorn)) {
  const driveLetter = aiDir[0].toLowerCase();
  const wslAiDir = `/mnt/${driveLetter}${aiDir.slice(2).replace(/\\/g, "/")}`;
  const wslCmd = `cd '${wslAiDir}' && export PYTHONPATH=.venv/lib/python3.14/site-packages:. && .venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --reload --port ${port}`;
  child = spawn("wsl", ["bash", "-c", wslCmd], {
    stdio: "inherit",
  });
} else {
  const command = process.platform === "win32" ? "uvicorn" : "uvicorn";
  child = spawn(command, ["app.main:app", "--reload", "--port", port], {
    cwd: aiDir,
    stdio: "inherit",
  });
}

child.on("exit", (code) => process.exit(code ?? 0));
child.on("error", (err) => {
  console.error(err);
  process.exit(1);
});
