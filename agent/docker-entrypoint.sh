#!/bin/sh
# Runs as root only long enough to make the data folder writable by the service user, then drops privileges.
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data /data/uploads
  chown -R app:app /data 2>/dev/null || true
  exec gosu app "$@"
fi
exec "$@"
