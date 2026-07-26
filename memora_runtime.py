"""Runtime adapters that let unmodified Memora use OpenClaw GLM and BGE-M3."""

from __future__ import annotations

import json
import re
import subprocess
import threading
from typing import Any, Dict, Optional, Sequence, Union


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _serialize_messages(messages: list[dict[str, Any]]) -> str:
    sections = []
    for message in messages:
        role = str(message.get("role", "user")).upper()
        content = message.get("content", "")
        rendered = (
            content
            if isinstance(content, str)
            else json.dumps(content, ensure_ascii=False)
        )
        sections.append(f"<{role}>\n{rendered}\n</{role}>")
    return "\n\n".join(sections)


def _schema_messages(
    messages: list[dict[str, Any]],
    response_format: Any,
) -> list[dict[str, Any]]:
    schema = json.dumps(
        response_format.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return [
        {
            "role": "system",
            "content": (
                "Return exactly one JSON object matching this JSON Schema. "
                "Do not include Markdown or explanatory text.\n"
                f"{schema}"
            ),
        },
        *messages,
    ]


def _validate_json(content: str, response_format: Any) -> Any:
    stripped = _JSON_FENCE.sub("", content.strip())
    try:
        return response_format.model_validate_json(stripped)
    except Exception:
        decoder = json.JSONDecoder()
        for start, char in enumerate(stripped):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(stripped[start:])
            except json.JSONDecodeError:
                continue
            return response_format.model_validate(value)
        raise ValueError(
            f"GLM returned invalid structured output for "
            f"{response_format.__name__}: {content[:500]}"
        )


class OpenClawChatCompletionModel:
    """Memora-compatible chat model that reuses OpenClaw Gateway credentials."""

    def __init__(self, cfg, token_usage_callback=None):
        self.cfg = cfg
        self.token_usage_callback = token_usage_callback

    def invoke(
        self,
        input: Union[str, Sequence[str]],
        prompt_args: Optional[Dict] = None,
        response_format: Any = None,
        source: str = "Unknown",
        **kwargs: Any,
    ) -> Any:
        del source
        if isinstance(input, str):
            content = input.format(**prompt_args) if prompt_args else input
            messages = [{"role": "user", "content": content}]
        elif isinstance(input, list):
            messages = input
        else:
            raise ValueError("Input must be a string or a list of messages.")

        request_messages = (
            _schema_messages(messages, response_format)
            if response_format
            else messages
        )
        content = self._run(request_messages, **kwargs)
        if not response_format:
            return content

        try:
            return _validate_json(content, response_format)
        except (ValueError, TypeError):
            repaired = self._run(
                [
                    *request_messages,
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "The previous JSON did not match the schema. "
                            "Return one corrected JSON object only."
                        ),
                    },
                ],
                **kwargs,
            )
            return _validate_json(repaired, response_format)

    def _run(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        openclaw_cfg = self.cfg.get("openclaw", {})
        command = str(openclaw_cfg.get("command", "openclaw"))
        model = str(self.cfg.llm.model)
        if "/" not in model:
            model = f"{openclaw_cfg.get('provider', 'zai')}/{model}"
        thinking = str(
            kwargs.get("thinking", self.cfg.llm.get("thinking", "off"))
        )
        completed = subprocess.run(
            [
                command,
                "infer",
                "model",
                "run",
                "--gateway",
                "--model",
                model,
                "--thinking",
                thinking,
                "--prompt",
                _serialize_messages(messages),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=int(openclaw_cfg.get("timeout", 600)),
        )
        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"OpenClaw GLM inference failed with exit code "
                f"{completed.returncode}: {error[:1000]}"
            )
        try:
            payload = json.loads(completed.stdout)
            outputs = payload.get("outputs") or []
            text = outputs[0].get("text") if outputs else None
        except (json.JSONDecodeError, AttributeError, IndexError) as error:
            raise RuntimeError(
                "OpenClaw GLM inference returned invalid JSON"
            ) from error
        if not isinstance(text, str):
            raise RuntimeError("OpenClaw GLM inference returned no text")
        return text


class BGEM3EmbeddingModel:
    """Memora-compatible dense embedding adapter backed by BAAI/bge-m3."""

    _models: dict[tuple[str, str, bool], Any] = {}
    _lock = threading.Lock()

    def __init__(self, cfg, client=None):
        del client
        self.cfg = cfg
        self.client = None
        self._model = None

    def get_client(self):
        return None

    def _load(self):
        embedding_cfg = self.cfg.get("embedding", {})
        model_name = str(embedding_cfg.get("model", "BAAI/bge-m3"))
        device = str(embedding_cfg.get("device", "cpu"))
        use_fp16 = bool(embedding_cfg.get("use_fp16", False))
        key = (model_name, device, use_fp16)
        if key not in self._models:
            with self._lock:
                if key not in self._models:
                    from FlagEmbedding import BGEM3FlagModel

                    options: dict[str, Any] = {"use_fp16": use_fp16}
                    if device and device != "auto":
                        options["devices"] = device
                    self._models[key] = BGEM3FlagModel(model_name, **options)
        self._model = self._models[key]

    def generate_embeddings(self, input: list[str]) -> list[list[float]]:
        if self._model is None:
            self._load()
        embedding_cfg = self.cfg.get("embedding", {})
        output = self._model.encode(
            input,
            batch_size=int(embedding_cfg.get("batch_size", 4)),
            max_length=int(embedding_cfg.get("max_length", 1024)),
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return [vector.tolist() for vector in output["dense_vecs"]]


def install_memora_runtime() -> None:
    """Patch Memora's two provider seams before its client modules are imported."""
    import memora.utils.embedding as embedding_module
    import memora.utils.llm as llm_module

    llm_module.ChatCompletionModel = OpenClawChatCompletionModel
    embedding_module.BaseEmbeddingModel = BGEM3EmbeddingModel

