#!/usr/bin/env bash
set -euo pipefail

target=/srv/personal-blog/mirror-platform/data/edge-health.ok
tmp="${target}.tmp"
if curl -fsS --max-time 10 https://gz-mirrors.maximoraverse.org/healthz | grep -q '"ok":true'; then
    printf 'ok\n' > "$tmp"
    chown 10001:10001 "$tmp"
    chmod 600 "$tmp"
    mv "$tmp" "$target"
else
    rm -f "$tmp" "$target"
    exit 1
fi
