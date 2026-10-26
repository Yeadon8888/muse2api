#!/bin/sh
set -eu

if [ -n "${MUSE2API_SOCKS_CONFIG:-}" ]; then
  proxy_out=/tmp/muse2api-proxy.out
  proxy_err=/tmp/muse2api-proxy.err
  : > "$proxy_out"
  : > "$proxy_err"
  node /app/deploy/windows/proxy-runner.mjs > "$proxy_out" 2> "$proxy_err" &
  proxy_pid=$!
  proxy_url=""
  attempts=0
  while [ "$attempts" -lt 100 ]; do
    if ! kill -0 "$proxy_pid" 2>/dev/null; then
      cat "$proxy_err" >&2
      exit 1
    fi
    proxy_url=$(head -n 1 "$proxy_out" 2>/dev/null || true)
    case "$proxy_url" in
      http://127.0.0.1:*) break ;;
    esac
    attempts=$((attempts + 1))
    sleep 0.1
  done
  case "$proxy_url" in
    http://127.0.0.1:*) ;;
    *) echo "Authenticated SOCKS bridge did not start" >&2; exit 1 ;;
  esac
  export MUSE2API_PROXY_SERVER="$proxy_url"
  export HTTP_PROXY="$proxy_url"
  export HTTPS_PROXY="$proxy_url"
  export NO_PROXY="127.0.0.1,localhost"
  unset MUSE2API_SOCKS_CONFIG
fi

exec python -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-18610}"
