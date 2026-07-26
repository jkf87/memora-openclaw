#!/usr/bin/env python3
"""Compile OpenClaw Markdown memory into a local Memora index."""

from __future__ import annotations

import argparse
import contextlib
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

from omegaconf import OmegaConf

from memora_runtime import install_memora_runtime


PLUGIN_DIR = Path(__file__).resolve().parent
DEFAULT_WORKSPACE = Path.home() / ".openclaw" / "workspace"
DEFAULT_DATA_DIR = Path.home() / ".openclaw" / "memora-openclaw"
DEFAULT_MEMORA_ROOT = PLUGIN_DIR / "vendor" / "Memora"


def source_files(workspace: Path) -> list[Path]:
    candidates = [workspace / "MEMORY.md"]
    memory_dir = workspace / "memory"
    if memory_dir.is_dir():
        candidates.extend(sorted(memory_dir.rglob("*.md")))
    return [path for path in candidates if path.is_file()]


def source_digest(paths: list[Path], workspace: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(workspace)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_config(args: argparse.Namespace, persist_path: Path):
    return OmegaConf.create(
        {
            "llm": {
                "provider": "openclaw_gateway",
                "model": args.model,
                "thinking": "off",
                "temperature": 0.0,
                "max_tokens": 4096,
            },
            "openclaw": {
                "command": args.openclaw_command,
                "provider": args.model.split("/", 1)[0],
                "timeout": 600,
            },
            "openai": {"api_type": "openai"},
            "embedding": {
                "provider": "ollama",
                "model": args.embedding_model,
                "base_url": args.ollama_base_url,
                "timeout_seconds": args.ollama_timeout_seconds,
            },
            "memory": {
                "backend": "local",
                "db_type": "chromadb",
                "memory_store": "openclaw-memora",
                "persist_path": str(persist_path),
                "collection_name": "openclaw_memora",
                "distance": "cosine",
                "query_score_threshold": 0.25,
                "update_score_threshold": 0.88,
                "force_rebuild": False,
                "enhance_query": False,
                "return_history": True,
                "multimodal_support": False,
                "top_k": 10,
                "cue_top_k": 10,
                "enable_hybrid_search": True,
                "hybrid_search_method": "bm25",
                "hybrid_top_k": 10,
                "bm25_score_threshold": 0.0,
                "enable_llm_filter": False,
                "enable_segmentation": False,
                "enable_episodic_memory": False,
                "use_segments_as_episodic": False,
                "enable_cue_index": True,
            },
            "retrieval": {
                "strategy": "prompt",
                "prompted_policy": {"max_steps": 4},
            },
            "eval": {"max_workers": 1},
        }
    )


def install_memora_import(memora_root: Path) -> None:
    source_root = memora_root / "src"
    if not source_root.is_dir():
        raise FileNotFoundError(
            f"Memora is not installed at {source_root}. "
            "Run scripts/install.sh first."
        )
    sys.path.insert(0, str(source_root))
    install_memora_runtime()


def split_text(text: str, max_chars: int = 48_000) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for block in text.split("\n\n"):
        addition = len(block) + (2 if current else 0)
        if current and current_size + addition > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_size = 0
        current.append(block)
        current_size += addition
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def read_state(data_dir: Path) -> dict:
    state_path = data_dir / "state.json"
    if not state_path.is_file():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_state(data_dir: Path, payload: dict) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    state_path = data_dir / "state.json"
    temporary = state_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, state_path)


def atomic_replace_index(staging: Path, target: Path) -> None:
    backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
    if target.exists():
        os.replace(target, backup)
    try:
        os.replace(staging, target)
    except Exception:
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def sync(args: argparse.Namespace) -> dict:
    workspace = Path(args.workspace).expanduser().resolve()
    data_dir = Path(args.data_dir).expanduser().resolve()
    memora_root = Path(args.memora_root).expanduser().resolve()
    paths = source_files(workspace)
    if not paths:
        raise RuntimeError(f"No OpenClaw memory files found under {workspace}")
    digest = source_digest(paths, workspace)
    state = read_state(data_dir)
    target = data_dir / "index"
    if not args.force and target.is_dir() and state.get("sourceDigest") == digest:
        return {
            "status": "unchanged",
            "files": len(paths),
            "digest": digest,
            "indexPath": str(target),
            "memoryCount": state.get("memoryCount", 0),
        }

    install_memora_import(memora_root)
    from memora.memora_client import MemoraClient

    data_dir.mkdir(parents=True, exist_ok=True)
    staging = data_dir / f".index.staging-{uuid.uuid4().hex}"
    started_at = time.time()
    built_entries = 0
    try:
        cfg = build_config(args, staging)
        with contextlib.redirect_stdout(sys.stderr):
            client = MemoraClient(cfg=cfg, user_id="openclaw-default")
            for file_number, path in enumerate(paths, start=1):
                relative = path.relative_to(workspace)
                text = path.read_text(encoding="utf-8", errors="replace")
                for part_number, chunk in enumerate(split_text(text), start=1):
                    metadata = {
                        "source_path": str(relative),
                        "source_mtime_ns": str(path.stat().st_mtime_ns),
                        "source_part": str(part_number),
                    }
                    entries = client.add(chunk, type="doc", metadata=metadata)
                    built_entries += len(entries)
                print(
                    f"[memora-sync] {file_number}/{len(paths)} {relative}",
                    file=sys.stderr,
                    flush=True,
                )
            memory_count = client.count()
        del client
        gc.collect()
        atomic_replace_index(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    payload = {
        "status": "rebuilt",
        "sourceDigest": digest,
        "files": len(paths),
        "builtEntries": built_entries,
        "memoryCount": memory_count,
        "model": args.model,
        "embeddingModel": args.embedding_model,
        "indexPath": str(target),
        "elapsedSeconds": round(time.time() - started_at, 3),
        "syncedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_state(data_dir, payload)
    return payload


def serialize_memory(entry) -> dict:
    return {
        "index": entry.index,
        "value": entry.value,
        "score": round(float(entry.score or 0.0), 6),
        "type": entry.memory_type,
        "timestamp": entry.timestamp,
        "cues": entry.get_cue_indices(),
    }


def query(args: argparse.Namespace) -> dict:
    data_dir = Path(args.data_dir).expanduser().resolve()
    index_path = data_dir / "index"
    if not index_path.is_dir():
        raise RuntimeError("Memora index is missing; run adapter.py sync first")
    install_memora_import(Path(args.memora_root).expanduser().resolve())
    from memora.memora_client import MemoraClient
    from memora.retriever.prompted_policy_retriever import PromptedPolicyRetriever

    cfg = build_config(args, index_path)
    started_at = time.time()
    with contextlib.redirect_stdout(sys.stderr):
        client = MemoraClient(cfg=cfg, user_id="openclaw-default")
        if args.strategy == "prompt":
            retriever = PromptedPolicyRetriever(cfg, memory_client=client._client)
            memories = retriever.retrieve(query=args.query, top_k=args.top_k)
            trace = retriever.get_trace()
        else:
            memories = client.query(
                args.query,
                top_k=args.top_k,
                enable_hybrid_search=True,
            )
            trace = [
                {
                    "step": 0,
                    "action": "SEMANTIC_RETRIEVE",
                    "query": args.query,
                    "memories_count": len(memories),
                }
            ]
        memory_count = client.count()

    workspace = Path(args.workspace).expanduser().resolve()
    paths = source_files(workspace)
    digest = source_digest(paths, workspace) if paths else None
    state = read_state(data_dir)
    return {
        "status": "ok",
        "strategy": args.strategy,
        "query": args.query,
        "results": [serialize_memory(entry) for entry in memories],
        "trace": trace,
        "index": {
            "memoryCount": memory_count,
            "files": state.get("files"),
            "syncedAt": state.get("syncedAt"),
            "stale": digest != state.get("sourceDigest"),
        },
        "elapsedSeconds": round(time.time() - started_at, 3),
    }


def status(args: argparse.Namespace) -> dict:
    data_dir = Path(args.data_dir).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve()
    paths = source_files(workspace)
    digest = source_digest(paths, workspace) if paths else None
    state = read_state(data_dir)
    return {
        "status": "ready" if (data_dir / "index").is_dir() else "missing",
        "indexPath": str(data_dir / "index"),
        "files": len(paths),
        "memoryCount": state.get("memoryCount", 0),
        "syncedAt": state.get("syncedAt"),
        "stale": digest != state.get("sourceDigest"),
    }


def doctor(args: argparse.Namespace) -> dict:
    from memora_runtime import OllamaEmbeddingModel

    cfg = build_config(args, Path(args.data_dir).expanduser() / "doctor-index")
    embeddings = OllamaEmbeddingModel(cfg).generate_embeddings(
        ["memora-openclaw embedding health check"]
    )
    return {
        "status": "ok",
        "embeddingProvider": "ollama",
        "embeddingModel": args.embedding_model,
        "ollamaBaseUrl": args.ollama_base_url,
        "dimensions": len(embeddings[0]),
    }


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    common.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    common.add_argument("--memora-root", default=str(DEFAULT_MEMORA_ROOT))
    common.add_argument("--model", default="zai/glm-5.2")
    common.add_argument("--openclaw-command", default="openclaw")
    common.add_argument("--embedding-model", default="bge-m3")
    common.add_argument(
        "--ollama-base-url",
        default="http://127.0.0.1:11434",
    )
    common.add_argument("--ollama-timeout-seconds", type=int, default=120)

    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    sync_parser = commands.add_parser("sync", parents=[common])
    sync_parser.add_argument("--force", action="store_true")
    query_parser = commands.add_parser("query", parents=[common])
    query_parser.add_argument("query")
    query_parser.add_argument("--top-k", type=int, default=8)
    query_parser.add_argument(
        "--strategy",
        choices=["semantic", "prompt"],
        default="semantic",
    )
    commands.add_parser("status", parents=[common])
    commands.add_parser("doctor", parents=[common])
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "sync":
            result = sync(args)
        elif args.command == "query":
            result = query(args)
        elif args.command == "doctor":
            result = doctor(args)
        else:
            result = status(args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": str(error),
                    "errorType": type(error).__name__,
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
