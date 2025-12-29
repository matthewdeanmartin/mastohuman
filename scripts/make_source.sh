#!/usr/bin/env bash
set -euo pipefail
#git2md src/github_is_my_cms \
#  --ignore __init__.py __pycache__ \
#  __about__.py logging_config.py py.typed utils \
#  --output SOURCE.md

black .
isort .
git2md . \
  --ignore __init__.py __pycache__ \
  .venv  .idea \
  dead_code data docs scripts \
  __about__.py logging_config.py py.typed utils \
  .markdownlintrc .gitignore  .pre-commit-config.yaml .ruff_cache README* \
  LICENSE SOURCE.md \
  .cache \
  uv.lock \
  --output SOURCE.md
