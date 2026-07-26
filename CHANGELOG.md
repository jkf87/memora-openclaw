# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and releases use [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-07-26

### Added

- OpenClaw skill with install, index, diagnose, compare, and rollback workflows
- One-command safe installer and explicit unattended full-bootstrap mode
- Ollama BGE-M3 embedding reuse through the local `/api/embed` endpoint
- Portable GLM invocation through the authenticated OpenClaw Gateway
- Automatic configuration backup and minimal fallback when `active-memory` is
  unavailable
- Release-readiness scoring and continuous integration
- Private-corpus benchmark report with statistical and interpretation limits

### Changed

- Reduced the Python runtime to the dependencies used by the OpenClaw adapter
- Pinned Microsoft Memora to a verified upstream revision

## [0.1.0] - 2026-07-26

### Added

- Initial OpenClaw `memora_recall` plugin and Memora adapter

[0.2.0]: https://github.com/jkf87/memora-openclaw/releases/tag/v0.2.0
[0.1.0]: https://github.com/jkf87/memora-openclaw/releases/tag/v0.1.0
