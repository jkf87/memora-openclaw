# Memora for OpenClaw

**Structured long-term memory for OpenClaw agents.**

[![Release](https://img.shields.io/github/v/release/jkf87/memora-openclaw)](https://github.com/jkf87/memora-openclaw/releases)
[![CI](https://github.com/jkf87/memora-openclaw/actions/workflows/ci.yml/badge.svg)](https://github.com/jkf87/memora-openclaw/actions/workflows/ci.yml)
[![OpenClaw](https://img.shields.io/badge/OpenClaw-2026.7.1%2B-blue)](https://github.com/openclaw/openclaw)
[![Ollama](https://img.shields.io/badge/Ollama-BGE--M3-black)](https://ollama.com/library/bge-m3)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

`memora-openclaw` turns your existing `MEMORY.md` and `memory/**/*.md` files
into Memora primary abstractions and cue anchors, then retrieves them through
Ollama BGE-M3. Markdown remains the source of truth: there is no memory
migration, no separate memory-cloud subscription, and no API key copied into
the plugin.

- LLM: a GLM model already authenticated in the OpenClaw Gateway
- Embeddings: an existing Ollama `bge-m3` model through `/api/embed`
- Vector store: local ChromaDB
- Credentials: no API key is copied into this plugin
- Source of truth: existing OpenClaw Markdown memory

## Why Memora for OpenClaw?

OpenClaw's built-in hybrid search is strong at exact strings, dates, and source
chunks. Memora adds a complementary representation layer for paraphrased,
semantic, and cross-language recall:

- **Structured retrieval** — primary abstractions preserve what a memory is
  about while multiple cue anchors provide semantic entry points.
- **No migration** — keep editing the same OpenClaw Markdown memory.
- **Reuse local embeddings** — use the Ollama BGE-M3 model you already run.
- **Reversible adoption** — disable the plugin without changing source memory.
- **Honest boundaries** — local embeddings and vector storage; GLM extraction
  uses your existing OpenClaw Gateway route.

In a 30-query personal-corpus evaluation, Memora reached **86.7% Complete@5**
versus **60.0%** for built-in hybrid search, with median direct-retrieval
latency of **0.96s** versus **2.42s**. The paired difference was not
statistically significant at 0.05 (`p=0.0768`), and hybrid remained better for
some exact facts. Read the full [methodology and limitations](docs/BENCHMARK.md).

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
   ChromaDB + Ollama BGE-M3
              |
              v
        memora_recall
              |
              v
 OpenClaw active-memory policy
```

## Requirements

- OpenClaw 2026.7.1 or newer
- Python 3.10, 3.11, or 3.12
- Git
- A running Ollama server with `bge-m3`
- A GLM route configured in OpenClaw, defaulting to `zai/glm-5.2`

The initial synchronization calls GLM to extract memories and may incur model
usage charges. Embeddings reuse the BGE-M3 model already managed by Ollama, so
the plugin does not download a second copy.

Prepare Ollama first:

```bash
ollama pull bge-m3
ollama serve
```

## Install

### Easy install

Install the skill globally with one command:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/jkf87/memora-openclaw/main/install.sh |
  bash
```

Then ask OpenClaw to finish setup and build the initial index:

```text
$memora-openclaw Install Memora, enable it, and build my initial index.
```

For an unattended full bootstrap, explicitly acknowledge configuration changes,
the BGE-M3 download, and possible GLM usage:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/jkf87/memora-openclaw/main/install.sh |
  bash -s -- --full --yes
```

### OpenClaw CLI

```bash
openclaw skills install \
  git:https://github.com/jkf87/memora-openclaw.git \
  --global
```

The skill checks prerequisites, prepares Ollama BGE-M3, installs the plugin,
backs up and patches OpenClaw configuration, builds the index, and verifies the
live `memora_recall` tool.

### Manual installation

```bash
git clone https://github.com/jkf87/memora-openclaw.git
cd memora-openclaw
./scripts/install.sh
```

The installer creates an isolated `.venv`, checks out a pinned Microsoft
Memora revision under `vendor/`, installs the Python dependencies, and links
the OpenClaw plugin.

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
`memora_recall` for semantic retrieval through Ollama BGE-M3.

If `active-memory` is not installed, the setup script applies a minimal profile
that exposes `memora_recall` without adding a policy controller.

## Verify

```bash
openclaw plugins doctor
openclaw gateway health
./.venv/bin/python ./adapter.py doctor
./.venv/bin/python ./adapter.py status
./.venv/bin/python ./adapter.py query \
  "What did we decide about the memory system?" \
  --strategy semantic
```

## Configuration

The defaults are portable and normally require no absolute paths:

- `model`: `zai/glm-5.2`
- `embeddingModel`: `bge-m3`
- `ollamaBaseUrl`: `http://127.0.0.1:11434`
- `ollamaTimeoutSeconds`: `120`
- `workspace`: `~/.openclaw/workspace`
- `dataDir`: `~/.openclaw/memora-openclaw`

Ollama owns CPU, Metal, or CUDA execution. The plugin only calls its HTTP API.
A remote Ollama server can be used by changing `ollamaBaseUrl`.

## Privacy

This repository contains no memory index, transcripts, user-specific
benchmarks, credentials, or OpenClaw configuration. `.gitignore` excludes the
local virtual environment, Memora checkout, generated indices, caches, and
private evaluation artifacts.

The initial sync sends source memory to the GLM route already configured in
OpenClaw so Memora can extract abstractions and cue anchors. Do not describe the
system as fully local unless that GLM route is also local.

## Project status

This project is an independent OpenClaw integration built on the
[Microsoft Memora](https://github.com/microsoft/Memora) research implementation.
The pinned upstream revision is fetched during installation and retains its own
MIT license.

- [Benchmark methodology](docs/BENCHMARK.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## Rollback

Disable `active-memory` or remove `memora_recall` from its `toolsAllow` list.
The plugin never modifies or deletes the source Markdown memory.

## License

MIT. Microsoft Memora is fetched separately and retains its own MIT license.
