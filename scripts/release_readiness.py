#!/usr/bin/env python3
"""Score release readiness and fail closed below the requested threshold."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable


ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Check:
    name: str
    weight: int
    run: Callable[[], tuple[bool, str]]
    critical: bool = False


def command(argv: list[str]) -> tuple[bool, str]:
    completed = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout.strip()
    return completed.returncode == 0, output


def required_files() -> tuple[bool, str]:
    names = [
        "README.md",
        "LICENSE",
        "SKILL.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/bug.yml",
        ".github/workflows/ci.yml",
    ]
    missing = [name for name in names if not (ROOT / name).is_file()]
    return not missing, "all present" if not missing else f"missing: {missing}"


def readme_positioning() -> tuple[bool, str]:
    text = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    phrases = [
        "structured long-term memory for openclaw",
        "openclaw memory",
        "easy install",
        "ollama bge-m3",
        "privacy",
        "benchmark",
        "limitations",
    ]
    missing = [phrase for phrase in phrases if phrase not in text]
    return not missing, "positioning complete" if not missing else f"missing: {missing}"


def version_consistency() -> tuple[bool, str]:
    package_version = json.loads(
        (ROOT / "package.json").read_text(encoding="utf-8")
    )["version"]
    plugin_version = json.loads(
        (ROOT / "openclaw.plugin.json").read_text(encoding="utf-8")
    )["version"]
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    ok = package_version == plugin_version and f"[{package_version}]" in changelog
    return ok, f"package={package_version}, plugin={plugin_version}"


def syntax_and_metadata() -> tuple[bool, str]:
    shell_files = [ROOT / "install.sh", *sorted((ROOT / "scripts").glob("*.sh"))]
    checks: list[tuple[bool, str]] = []
    checks.append(command(["bash", "-n", *[str(path) for path in shell_files]]))
    checks.append(command(["node", "--check", "index.js"]))
    for json_file in ("package.json", "openclaw.plugin.json"):
        try:
            json.loads((ROOT / json_file).read_text(encoding="utf-8"))
            checks.append((True, json_file))
        except (OSError, json.JSONDecodeError) as error:
            checks.append((False, f"{json_file}: {error}"))
    failed = [detail for ok, detail in checks if not ok]
    return not failed, "syntax valid" if not failed else " | ".join(failed)


def unit_tests() -> tuple[bool, str]:
    return command([sys.executable, "-m", "pytest", "-q", "tests"])


def easy_install_dry_run() -> tuple[bool, str]:
    ok, output = command(
        ["bash", "install.sh", "--full", "--yes", "--dry-run"]
    )
    expected = [
        "openclaw",
        "skills",
        "install",
        "memora-openclaw.git",
        "--global",
        "--apply-config",
        "--sync",
    ]
    missing = [token for token in expected if token not in output]
    return ok and not missing, output if not missing else f"missing {missing}: {output}"


def package_artifact() -> tuple[bool, str]:
    ok, output = command(["npm", "pack", "--dry-run", "--json"])
    if not ok:
        return False, output
    try:
        json_start = output.find("[")
        if json_start < 0:
            raise ValueError("JSON array not found")
        decoded, _ = json.JSONDecoder().raw_decode(output[json_start:])
        payload = decoded[0]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        return False, f"invalid npm pack output: {error}"
    paths = {item["path"] for item in payload.get("files", [])}
    required = {"README.md", "SKILL.md", "install.sh", "scripts/setup.sh"}
    forbidden_parts = {".venv", "vendor", "evaluation/private", "data"}
    forbidden = [
        path for path in paths if any(part in path for part in forbidden_parts)
    ]
    missing = sorted(required - paths)
    passed = not missing and not forbidden
    return passed, (
        f"{len(paths)} files, {payload.get('size')} bytes"
        if passed
        else f"missing={missing}, forbidden={forbidden}"
    )


def privacy_and_secrets() -> tuple[bool, str]:
    ok, output = command(["git", "ls-files", "-co", "--exclude-standard"])
    if not ok:
        return False, output
    patterns = {
        "absolute macOS user path": re.compile(r"/" r"Users/[^/\s]+/"),
        "GitHub token": re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
        "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        "email address": re.compile(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE
        ),
    }
    findings: list[str] = []
    for relative in output.splitlines():
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in patterns.items():
            if pattern.search(text):
                findings.append(f"{relative}: {label}")
    return not findings, "no private markers" if not findings else "; ".join(findings)


def skill_manifest() -> tuple[bool, str]:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not frontmatter:
        return False, "missing YAML frontmatter"
    block = frontmatter.group(1)
    has_name = re.search(r"^name:\s*memora-openclaw\s*$", block, re.MULTILINE)
    has_description = re.search(r"^description:\s*\S+", block, re.MULTILINE)
    extra_keys = [
        line.split(":", 1)[0]
        for line in block.splitlines()
        if ":" in line and line.split(":", 1)[0] not in {"name", "description"}
    ]
    passed = bool(has_name and has_description and not extra_keys)
    return passed, "valid" if passed else f"unexpected keys: {extra_keys}"


def git_hygiene() -> tuple[bool, str]:
    return command(["git", "diff", "--check"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-score", type=int, default=95)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    checks = [
        Check("open-source files", 10, required_files),
        Check("README positioning", 10, readme_positioning),
        Check("version consistency", 10, version_consistency, critical=True),
        Check("syntax and metadata", 10, syntax_and_metadata, critical=True),
        Check("unit tests", 15, unit_tests, critical=True),
        Check("easy installer dry run", 10, easy_install_dry_run, critical=True),
        Check("package artifact", 10, package_artifact, critical=True),
        Check("privacy and secrets", 15, privacy_and_secrets, critical=True),
        Check("skill manifest", 5, skill_manifest, critical=True),
        Check("git hygiene", 5, git_hygiene),
    ]

    results = []
    score = 0
    critical_failures = []
    for check in checks:
        try:
            passed, detail = check.run()
        except Exception as error:  # fail closed and keep the complete scorecard
            passed, detail = False, f"{type(error).__name__}: {error}"
        if passed:
            score += check.weight
        elif check.critical:
            critical_failures.append(check.name)
        results.append(
            {
                "name": check.name,
                "passed": passed,
                "weight": check.weight,
                "detail": detail,
                "critical": check.critical,
            }
        )

    passed = score >= args.min_score and not critical_failures
    payload = {
        "score": score,
        "minimum": args.min_score,
        "passed": passed,
        "critical_failures": critical_failures,
        "checks": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in results:
            status = "PASS" if item["passed"] else "FAIL"
            print(
                f"[{status}] {item['name']} "
                f"({item['weight']}): {item['detail']}"
            )
        print(f"\nRelease readiness: {score}/100 (minimum {args.min_score})")
        if critical_failures:
            print(f"Critical failures: {', '.join(critical_failures)}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
