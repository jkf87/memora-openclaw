"""Runtime adapters that let unmodified Memora use OpenClaw GLM and BGE-M3."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Dict, Optional, Sequence, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


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


class OllamaEmbeddingModel:
    """Memora-compatible adapter for an existing Ollama embedding model."""

    def __init__(self, cfg, client=None):
        del client
        self.cfg = cfg
        self.client = None

    def get_client(self):
        return None

    def generate_embeddings(self, input: list[str]) -> list[list[float]]:
        embedding_cfg = self.cfg.get("embedding", {})
        base_url = str(
            embedding_cfg.get("base_url", "http://127.0.0.1:11434")
        ).rstrip("/") + "/"
        endpoint = urljoin(base_url, "api/embed")
        payload = json.dumps(
            {
                "model": str(embedding_cfg.get("model", "bge-m3")),
                "input": input,
                "truncate": True,
            }
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(
                request,
                timeout=int(embedding_cfg.get("timeout_seconds", 120)),
            ) as response:
                output = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama embedding request failed with HTTP "
                f"{error.code}: {details[:500]}"
            ) from error
        except URLError as error:
            raise RuntimeError(
                f"Cannot reach Ollama at {base_url}. Start Ollama or configure "
                "embedding.base_url."
            ) from error

        embeddings = output.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(input):
            raise RuntimeError(
                "Ollama returned an invalid embedding batch: expected "
                f"{len(input)} vectors"
            )
        if any(
            not isinstance(vector, list)
            or not vector
            or any(not isinstance(value, (int, float)) for value in vector)
            for vector in embeddings
        ):
            raise RuntimeError("Ollama returned invalid embedding vectors")
        return embeddings


def install_memora_runtime() -> None:
    """Patch Memora's two provider seams before its client modules are imported."""
    import memora.utils.embedding as embedding_module
    import memora.utils.llm as llm_module

    llm_module.ChatCompletionModel = OpenClawChatCompletionModel
    embedding_module.BaseEmbeddingModel = OllamaEmbeddingModel
