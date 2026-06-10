#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
VENV_DIR="${VENV_DIR:-.venv312}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install -r requirements-dev.txt

echo "Running tests..."
"$VENV_DIR/bin/python" -m pytest -q

echo
echo "Starting BrightEdge crawler API..."
echo "Health: http://$HOST:$PORT/health"
echo "Docs:   http://$HOST:$PORT/docs"
echo
echo "Example:"
echo "curl -X POST http://$HOST:$PORT/crawl -H 'Content-Type: application/json' -d '{\"url\":\"https://example.com\"}'"
echo

exec "$VENV_DIR/bin/uvicorn" crawler.main:app --host "$HOST" --port "$PORT"
