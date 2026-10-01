#!/usr/bin/env bash
set -euo pipefail

base=https://mirrors.maximoraverse.org/internal-edge-sync
staging=/srv/mirror-edge/staging
incoming=/srv/mirror-edge/files.incoming
live=/srv/mirror-edge/files

install -d -m 700 "$staging"
aria2c \
  --continue=true \
  --max-connection-per-server=16 \
  --split=16 \
  --min-split-size=4M \
  --max-tries=20 \
  --retry-wait=15 \
  --file-allocation=none \
  --auto-file-renaming=false \
  --allow-overwrite=true \
  --dir="$staging" \
  --out=releases.tar \
  "$base/releases.tar"
curl -fsS -o "$staging/releases.tar.sha256" "$base/releases.tar.sha256"
(cd "$staging" && sha256sum -c releases.tar.sha256)

rm -rf "$incoming"
install -d -m 750 -o www-data -g www-data "$incoming/github"
tar -C "$incoming/github" -xf "$staging/releases.tar"
chown -R www-data:www-data "$incoming"

python3 - "$incoming/github" /srv/mirror-edge/mirror.db <<'PY'
import hashlib, pathlib, sqlite3, sys
root = pathlib.Path(sys.argv[1])
con = sqlite3.connect(sys.argv[2])
rows = con.execute("select local_path,size,sha256 from artifacts where storage_provider='local' and local_path like 'github/%'").fetchall()
for local_path, size, digest in rows:
    path = root.parent / local_path
    if not path.is_file() or path.stat().st_size != size:
        raise SystemExit(f"missing-or-size-mismatch:{local_path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise SystemExit(f"digest-mismatch:{local_path}")
print(f"verified={len(rows)}")
PY

old=/srv/mirror-edge/files.previous
rm -rf "$old"
if [[ -d "$live" ]]; then mv "$live" "$old"; fi
mv "$incoming" "$live"
systemctl restart mirror-edge
curl -fsS http://127.0.0.1:18080/healthz >/dev/null
date -u +%FT%TZ > /srv/mirror-edge/sync-complete
