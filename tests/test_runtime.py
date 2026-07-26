import json
import sys
import types
from unittest.mock import patch

import numpy
from omegaconf import OmegaConf
from pydantic import BaseModel

from memora_runtime import BGEM3EmbeddingModel, OpenClawChatCompletionModel


def config():
    return OmegaConf.create(
        {
            "llm": {"model": "zai/glm-5.2", "thinking": "off"},
            "openclaw": {"command": "openclaw", "provider": "zai", "timeout": 5},
            "embedding": {
                "model": "BAAI/bge-m3",
                "device": "cpu",
                "use_fp16": False,
                "batch_size": 2,
                "max_length": 1024,
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


def test_bge_m3_returns_dense_vectors(monkeypatch):
    class FakeModel:
        def __init__(self, model_name, **options):
            assert model_name == "BAAI/bge-m3"
            assert options == {"use_fp16": False, "devices": "cpu"}

        def encode(self, values, **options):
            assert values == ["한국어", "English"]
            assert options["return_sparse"] is False
            assert options["return_colbert_vecs"] is False
            return {
                "dense_vecs": numpy.array(
                    [[1.0, 0.0], [0.0, 1.0]],
                    dtype=numpy.float32,
                )
            }

    monkeypatch.setitem(
        sys.modules,
        "FlagEmbedding",
        types.SimpleNamespace(BGEM3FlagModel=FakeModel),
    )
    BGEM3EmbeddingModel._models.clear()

    vectors = BGEM3EmbeddingModel(config()).generate_embeddings(
        ["한국어", "English"]
    )

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]

