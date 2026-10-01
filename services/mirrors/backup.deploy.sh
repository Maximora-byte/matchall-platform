#!/usr/bin/env bash
set -euo pipefail
umask 077

cd /srv/personal-blog
set -a
source ./.env
set +a

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p backups

docker compose exec -T mariadb mariadb-dump \
  -u"${WORDPRESS_DB_USER:-bloguser}" \
  -p"${WORDPRESS_DB_PASSWORD:?WORDPRESS_DB_PASSWORD not set}" \
  "${WORDPRESS_DB_NAME:-wordpress}" > "backups/db-${stamp}.sql"

tar -czf "backups/wp-content-${stamp}.tar.gz" wp-content

nextcloud_maintenance=0
cleanup_nextcloud_maintenance() {
  if [[ "$nextcloud_maintenance" == "1" ]]; then
    docker compose exec -T -u www-data nextcloud php occ maintenance:mode --off >/dev/null || true
  fi
}
trap cleanup_nextcloud_maintenance EXIT

docker compose exec -T -u www-data nextcloud php occ maintenance:mode --on >/dev/null
nextcloud_maintenance=1
docker compose exec -T nextcloud-postgres pg_dump \
  -U nextcloud -d nextcloud -Fc > "backups/nextcloud-db-${stamp}.dump"
tar -czf "backups/nextcloud-files-${stamp}.tar.gz" \
  nextcloud/html/config \
  nextcloud/html/custom_apps \
  nextcloud/html/data \
  nextcloud/html/themes
docker compose exec -T -u www-data nextcloud php occ maintenance:mode --off >/dev/null
nextcloud_maintenance=0

docker compose exec -T mirrors python -c \
  "import sqlite3; src=sqlite3.connect('/data/mirror.db'); dst=sqlite3.connect('/data/mirror-backup.db'); src.backup(dst); dst.close(); src.close()"
mv mirror-platform/data/mirror-backup.db "backups/mirrors-db-${stamp}.sqlite"
tar -czf "backups/mirrors-files-${stamp}.tar.gz" mirror-platform/data/files

find backups -type f -mtime +14 -delete

echo "backup complete: ${stamp}"
