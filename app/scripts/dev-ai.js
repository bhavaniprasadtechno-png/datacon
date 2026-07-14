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
const venvUvicorn =
  process.platform === "win32"
    ? path.join(aiDir, ".venv", "Scripts", "uvicorn.exe")
    : path.join(aiDir, ".venv", "bin", "uvicorn");

const command = fs.existsSync(venvUvicorn) ? venvUvicorn : "uvicorn";
const port = process.env.AI_DEV_PORT || "8000";

const child = spawn(command, ["app.main:app", "--reload", "--port", port], {
  cwd: aiDir,
  stdio: "inherit",
});

child.on("exit", (code) => process.exit(code ?? 0));
child.on("error", (err) => {
  console.error(err);
  process.exit(1);
});
