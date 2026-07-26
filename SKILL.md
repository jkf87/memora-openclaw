---
name: memora-openclaw
description: Install, configure, index, verify, operate, or roll back Memora retrieval for OpenClaw using an existing GLM route and Ollama BGE-M3. Use when an OpenClaw user asks to add Memora memory, rebuild or diagnose the Memora index, enable memora_recall or active-memory retrieval, migrate the setup to another OpenClaw installation, or compare Memora with builtin memory search.
---

# Memora for OpenClaw

Resolve `skill_dir` as the directory containing this `SKILL.md`. Run bundled
scripts from that directory; do not assume the current working directory.

## Install and activate

1. Run `bash "$skill_dir/scripts/setup.sh" --check-only`.
2. If Ollama is stopped, rerun with `--start-ollama`.
3. If `bge-m3` is absent, rerun with `--pull-model`. Warn that the model is
   roughly 1.2 GB before downloading it.
4. For a complete requested installation, run:

   ```bash
   bash "$skill_dir/scripts/setup.sh" \
     --start-ollama \
     --pull-model \
     --apply-config \
     --sync
   ```

5. Explain that the first `--sync` invokes the configured GLM route to extract
   memories and may incur API usage. Continue automatically when the user
   explicitly asked for installation plus indexing.
6. Run `bash "$skill_dir/scripts/verify.sh"` before reporting completion.

The setup script backs up `~/.openclaw/openclaw.json` before changing it. It
uses the full active-memory policy when that plugin exists and otherwise
applies a minimal configuration that exposes `memora_recall`.

## Operate the index

Use the plugin-local virtual environment:

```bash
"$skill_dir/.venv/bin/python" "$skill_dir/adapter.py" status
"$skill_dir/.venv/bin/python" "$skill_dir/adapter.py" sync
"$skill_dir/.venv/bin/python" "$skill_dir/adapter.py" sync --force
```

- Use ordinary `sync` after Markdown memory changes; it skips unchanged input.
- Use `--force` only for an embedding-model change, damaged index, or explicit
  rebuild request.
- Treat `MEMORY.md` and `memory/**/*.md` as the source of truth. Never edit or
  delete them while maintaining the Memora index.

For a private smoke test, run one semantic query and inspect only whether the
expected fact is present:

```bash
"$skill_dir/.venv/bin/python" "$skill_dir/adapter.py" query \
  "<user-approved memory question>" --strategy semantic --top-k 5
```

Do not paste raw private memories into public logs, issues, or repositories.

## Diagnose

Run:

```bash
bash "$skill_dir/scripts/verify.sh"
openclaw memory status --json
```

Interpret failures in this order:

1. Ollama server unavailable or `bge-m3` missing.
2. Plugin-local `.venv` or pinned `vendor/Memora` missing.
3. OpenClaw plugin not loaded or configuration invalid.
4. Index missing or stale.
5. GLM route unavailable during synchronization.

Do not rebuild until the failing prerequisite is confirmed.

## Compare with builtin memory

Use identical questions and top-k for both systems:

```bash
openclaw memory search --agent main --json --max-results 5 "<question>"
"$skill_dir/.venv/bin/python" "$skill_dir/adapter.py" query \
  "<question>" --strategy semantic --top-k 5
```

Measure evidence completeness, first relevant rank, and wall latency. For final
answer tests, force `memory_search` or `memora_recall` separately and require
the answer to be supported by that tool's returned evidence. Keep any
personal-corpus evaluation set outside this repository.

## Roll back

Prefer reversible disablement:

```bash
openclaw plugins disable memora-openclaw
openclaw gateway restart
```

Restore the timestamped configuration backup created under
`~/.openclaw/backups/memora-openclaw/` only when the user explicitly requests
restoration. Do not delete `~/.openclaw/memora-openclaw` unless explicitly
asked; it contains only the derived index and can be rebuilt.

