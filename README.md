# Memora for OpenClaw

`memora-openclaw` adds Memora retrieval to OpenClaw without replacing
OpenClaw's Markdown memory. It compiles `MEMORY.md` and `memory/**/*.md` into
Memora primary abstractions and cue indices, then exposes them through the
optional `memora_recall` tool.

- LLM: a GLM model already authenticated in the OpenClaw Gateway
- Embeddings: local `BAAI/bge-m3` through FlagEmbedding
- Vector store: local ChromaDB
- Credentials: no API key is copied into this plugin
- Source of truth: existing OpenClaw Markdown memory

## How it works

```text
MEMORY.md / memory/**/*.md
              |
              v
       Memora extraction ----> OpenClaw Gateway ----> GLM
              |
              v
  primary memories + cue indices
              |
              v
      ChromaDB + BGE-M3
              |
              v
        memora_recall
              |
              v
 OpenClaw active-memory policy
```

## Requirements

- OpenClaw 2026.7.1 or newer
- Python 3.10 or newer
- Git
- A GLM route configured in OpenClaw, defaulting to `zai/glm-5.2`
- Enough disk space for Memora dependencies and the BGE-M3 model

The initial synchronization calls GLM to extract memories and may incur model
usage charges. BGE-M3 runs locally.

## Install

```bash
git clone https://github.com/YOUR_ACCOUNT/memora-openclaw.git
cd memora-openclaw
./scripts/install.sh
```

The installer creates an isolated `.venv`, checks out a pinned Microsoft
Memora revision under `vendor/`, installs BGE-M3 support, and links the OpenClaw
plugin.

## Build the index

```bash
./.venv/bin/python ./adapter.py sync
```

Index data is written to `~/.openclaw/memora-openclaw`, outside the repository.
Run `sync` again after changing OpenClaw memory. Unchanged memory is detected
by a content digest and skipped.

## Enable automatic retrieval

Review the configuration first:

```bash
openclaw config patch \
  --file ./config/openclaw.patch.json5 \
  --dry-run
```

Then apply it:

```bash
openclaw config patch --file ./config/openclaw.patch.json5
```

The profile uses `active-memory` as a bounded GLM policy controller and
`memora_recall` for BGE-M3 semantic retrieval.

## Verify

```bash
openclaw plugins doctor
openclaw gateway health
./.venv/bin/python ./adapter.py status
./.venv/bin/python ./adapter.py query \
  "What did we decide about the memory system?" \
  --strategy semantic
```

## Configuration

The defaults are portable and normally require no absolute paths:

- `model`: `zai/glm-5.2`
- `embeddingModel`: `BAAI/bge-m3`
- `embeddingDevice`: `cpu`
- `embeddingMaxLength`: `1024`
- `workspace`: `~/.openclaw/workspace`
- `dataDir`: `~/.openclaw/memora-openclaw`

CUDA users may set `embeddingDevice` to `cuda:0`. CPU is the conservative
default.

## Privacy

This repository contains no memory index, transcripts, user-specific
benchmarks, credentials, or OpenClaw configuration. `.gitignore` excludes the
local virtual environment, Memora checkout, generated indices, caches, and
private evaluation artifacts.

## Rollback

Disable `active-memory` or remove `memora_recall` from its `toolsAllow` list.
The plugin never modifies or deletes the source Markdown memory.

## License

MIT. Microsoft Memora is fetched separately and retains its own MIT license.
