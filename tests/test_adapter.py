from argparse import Namespace
from pathlib import Path

import adapter


def arguments() -> Namespace:
    return Namespace(
        model="zai/glm-5.2",
        openclaw_command="openclaw",
        embedding_model="bge-m3",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_timeout_seconds=120,
    )


def test_source_files_are_recursive_and_exclude_unrelated_markdown(tmp_path):
    workspace = tmp_path / "workspace"
    nested = workspace / "memory" / "projects"
    nested.mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("root", encoding="utf-8")
    (nested / "project.md").write_text("nested", encoding="utf-8")
    (workspace / "notes.md").write_text("ignored", encoding="utf-8")

    paths = adapter.source_files(workspace)

    assert [path.relative_to(workspace).as_posix() for path in paths] == [
        "MEMORY.md",
        "memory/projects/project.md",
    ]


def test_digest_is_workspace_relative(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    for workspace in (first, second):
        memory = workspace / "memory"
        memory.mkdir(parents=True)
        (memory / "same.md").write_text("same content", encoding="utf-8")

    assert adapter.source_digest(
        adapter.source_files(first), first
    ) == adapter.source_digest(adapter.source_files(second), second)


def test_config_uses_glm_and_bge_m3(tmp_path):
    cfg = adapter.build_config(arguments(), tmp_path / "index")

    assert cfg.llm.model == "zai/glm-5.2"
    assert cfg.llm.provider == "openclaw_gateway"
    assert cfg.embedding.provider == "ollama"
    assert cfg.embedding.model == "bge-m3"
    assert cfg.embedding.base_url == "http://127.0.0.1:11434"
