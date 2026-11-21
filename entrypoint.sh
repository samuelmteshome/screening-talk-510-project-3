#!/bin/sh
set -e
case "$1" in
  train) shift; exec python -m src.train "$@" ;;
  serve) exec uvicorn src.api.main:app --host 0.0.0.0 --port "${PORT:-8080}" ;;
  *) exec "$@" ;;
esac
