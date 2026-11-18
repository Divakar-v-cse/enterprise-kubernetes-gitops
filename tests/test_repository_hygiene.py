"""Guard rails: no secrets, kubeconfigs or environment files in the repo."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache", "rendered"}

FORBIDDEN_NAMES = {".env", "kubeconfig", "id_rsa", "id_ed25519"}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\baws_secret_access_key\s*=\s*[A-Za-z0-9/+=]{20,}"),
    re.compile(r"(?i)\bghp_[A-Za-z0-9]{30,}"),
    re.compile(r"(?i)password\s*=\s*['\"][^'\"$]{8,}['\"]"),
]


def _files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def test_no_forbidden_files_are_present() -> None:
    offenders = [str(p.relative_to(ROOT)) for p in _files() if p.name in FORBIDDEN_NAMES]
    assert not offenders, f"secret-bearing files present: {offenders}"


def test_no_private_keys_or_credentials_in_source() -> None:
    offenders: list[str] = []
    for path in _files():
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".gz"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    assert not offenders, "possible credentials committed:\n" + "\n".join(offenders)


def test_gitignore_covers_runtime_artifacts() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in (".env", "node_modules/", "*.pem", "kubeconfig", "__pycache__/"):
        assert entry in gitignore


def test_secret_example_uses_placeholders_only() -> None:
    example = (ROOT / "kubernetes" / "base" / "secret.example.yaml").read_text(encoding="utf-8")
    assert example.count("REPLACE_ME") >= 4
