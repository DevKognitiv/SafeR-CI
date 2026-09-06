#!/bin/bash
set -euo pipefail

# Only run in Claude Code on the web (remote sessions)
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# Backend: Python dependencies + pylint (used by .github/workflows/pylint.yml)
pip3 install --quiet -r backend/requirements.txt pylint

# Web dashboard: Node dependencies (Next.js, ESLint)
npm install --prefix web-dashboard --no-audit --no-fund

# Let pylint and other tools resolve the backend's `app.*` package imports
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PYTHONPATH=\"$CLAUDE_PROJECT_DIR/backend\"" >> "$CLAUDE_ENV_FILE"
fi

# Mobile (Flutter) is skipped: the Flutter SDK is not available in this environment.

echo "SafeR-CI session setup complete"
