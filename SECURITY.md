# Security policy

## Supported versions

Security fixes are provided for the latest release.

## Reporting a vulnerability

Please use GitHub private vulnerability reporting for this repository. Do not
open a public issue containing credentials, private OpenClaw memory, exploit
details, or unredacted logs.

Reports should include affected versions, impact, reproduction steps, and any
suggested mitigation. You should receive an acknowledgement within seven days.

## Data boundary

The plugin reads OpenClaw Markdown memory, sends it to the GLM route configured
in OpenClaw during indexing, and stores derived ChromaDB data under
`~/.openclaw/memora-openclaw`. Ollama BGE-M3 embeddings are local by default.
Review the configured GLM route before indexing sensitive memory.
