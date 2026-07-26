import json
import types
from unittest.mock import patch

from omegaconf import OmegaConf
from pydantic import BaseModel

from memora_runtime import OllamaEmbeddingModel, OpenClawChatCompletionModel


def config():
    return OmegaConf.create(
        {
            "llm": {"model": "zai/glm-5.2", "thinking": "off"},
            "openclaw": {"command": "openclaw", "provider": "zai", "timeout": 5},
            "embedding": {
                "model": "bge-m3",
                "base_url": "http://127.0.0.1:11434",
                "timeout_seconds": 120,
            },
        }
    )


def test_glm_uses_openclaw_gateway():
    completed = types.SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"outputs": [{"text": "remembered"}]}),
        stderr="",
    )
    with patch("memora_runtime.subprocess.run", return_value=completed) as run:
        result = OpenClawChatCompletionModel(config()).invoke("Recall this")

    assert result == "remembered"
    argv = run.call_args.args[0]
    assert argv[:5] == ["openclaw", "infer", "model", "run", "--gateway"]
    assert "zai/glm-5.2" in argv


def test_glm_validates_structured_output():
    class Answer(BaseModel):
        value: str

    completed = types.SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"outputs": [{"text": '{"value":"ok"}'}]}),
        stderr="",
    )
    with patch("memora_runtime.subprocess.run", return_value=completed):
        result = OpenClawChatCompletionModel(config()).invoke(
            "Return JSON",
            response_format=Answer,
        )

    assert result.value == "ok"


def test_ollama_bge_m3_returns_dense_vectors():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(
                {
                    "model": "bge-m3",
                    "embeddings": [[1.0, 0.0], [0.0, 1.0]],
                }
            ).encode("utf-8")

    with patch("memora_runtime.urlopen", return_value=FakeResponse()) as urlopen:
        vectors = OllamaEmbeddingModel(config()).generate_embeddings(
            ["한국어", "English"]
        )

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    request = urlopen.call_args.args[0]
    payload = json.loads(request.data)
    assert request.full_url == "http://127.0.0.1:11434/api/embed"
    assert payload == {
        "model": "bge-m3",
        "input": ["한국어", "English"],
        "truncate": True,
    }
