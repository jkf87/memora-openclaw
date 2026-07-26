import { spawn } from "node:child_process";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const pluginDir = dirname(fileURLToPath(import.meta.url));
const adapterPath = join(pluginDir, "adapter.py");
const defaultPython = join(
  pluginDir,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const defaultMemoraRoot = join(pluginDir, "vendor", "Memora");
const defaultWorkspace = join(homedir(), ".openclaw", "workspace");
const defaultDataDir = join(homedir(), ".openclaw", "memora-openclaw");

function runAdapter(args, config, signal) {
  const python = config.pythonPath || defaultPython;
  const timeoutMs = config.timeoutMs || 120000;
  const childArgs = [
    adapterPath,
    ...args,
    "--workspace",
    config.workspace || defaultWorkspace,
    "--data-dir",
    config.dataDir || defaultDataDir,
    "--memora-root",
    config.memoraRoot || defaultMemoraRoot,
    "--model",
    config.model || "zai/glm-5.2",
    "--openclaw-command",
    config.openclawCommand || "openclaw",
    "--embedding-model",
    config.embeddingModel || "BAAI/bge-m3",
    "--embedding-device",
    config.embeddingDevice || "cpu",
    "--embedding-max-length",
    String(config.embeddingMaxLength || 1024),
  ];

  return new Promise((resolve, reject) => {
    const child = spawn(python, childArgs, {
      stdio: ["ignore", "pipe", "pipe"],
      env: process.env,
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`Memora adapter timed out after ${timeoutMs} ms`));
    }, timeoutMs);
    timer.unref?.();

    const abort = () => child.kill("SIGTERM");
    signal?.addEventListener("abort", abort, { once: true });
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      let payload;
      try {
        payload = JSON.parse(stdout.trim());
      } catch {
        reject(
          new Error(
            `Memora adapter returned invalid JSON: ${(stderr || stdout).slice(0, 1000)}`,
          ),
        );
        return;
      }
      if (code !== 0 || payload.status === "error") {
        reject(
          new Error(
            payload.error ||
              stderr.trim() ||
              `Memora adapter exited with code ${code}`,
          ),
        );
        return;
      }
      resolve(payload);
    });
  });
}

export default definePluginEntry({
  id: "memora-openclaw",
  name: "Memora for OpenClaw",
  description:
    "Retrieves OpenClaw memories through Memora using GLM and BGE-M3.",
  register(api) {
    const config = api.pluginConfig || {};
    api.registerTool(
      {
        name: "memora_recall",
        label: "Memora Recall",
        description:
          "Search long-term OpenClaw memory through Memora primary abstractions and cue anchors. Start with semantic retrieval and reformulate only when evidence is incomplete.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {
            query: {
              type: "string",
              description: "A concise, self-contained memory search query.",
            },
            topK: {
              type: "integer",
              minimum: 1,
              maximum: 20,
            },
            strategy: {
              type: "string",
              enum: ["semantic", "prompt"],
            },
          },
          required: ["query"],
        },
        async execute(_id, params, signal) {
          const payload = await runAdapter(
            [
              "query",
              params.query,
              "--top-k",
              String(params.topK || config.topK || 8),
              "--strategy",
              params.strategy || "semantic",
            ],
            config,
            signal,
          );
          return {
            content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
            details: payload,
          };
        },
      },
      { optional: true },
    );
  },
});

