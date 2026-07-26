# Contributing

Contributions are welcome, especially portability fixes, retrieval evaluations,
and OpenClaw compatibility improvements.

## Development setup

```bash
git clone https://github.com/jkf87/memora-openclaw.git
cd memora-openclaw
bash scripts/install.sh
./.venv/bin/python -m pip install "pytest>=8,<10"
./.venv/bin/python -m pytest -q
python3 scripts/release_readiness.py --min-score 95
```

## Pull requests

- Keep generated indices, memory files, credentials, and private evaluation
  cases outside the repository.
- Add or update tests for behavior changes.
- Run the release-readiness check before opening a pull request.
- Explain user-visible behavior and any OpenClaw, Memora, GLM, or Ollama
  compatibility impact.

## Reporting retrieval results

Include the corpus boundary, query count, model and embedding versions, scoring
method, latency definition, and statistical test. Do not publish private memory
content or describe personal-corpus results as a public benchmark or SOTA.
