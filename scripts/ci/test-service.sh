#!/usr/bin/env bash
# Run one service's test suite in an isolated Python container.
# Usage: scripts/ci/test-service.sh applications/user-service
set -euo pipefail
service="${1:?usage: test-service.sh <service-dir>}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

docker run --rm \
  -v "${repo_root}:/src" \
  -w "/src/${service}" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  python:3.12-slim \
  sh -c "pip install --quiet -r /src/requirements-dev.txt && python -m pytest -q"
