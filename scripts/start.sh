#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${LEGAL_BLOG_PORT:-8000}" --no-access-log
