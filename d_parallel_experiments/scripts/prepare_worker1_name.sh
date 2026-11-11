#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Run with sudo.'; exit 1; }
case "$(hostnamectl --static)" in
  lishuo-server|spark-worker-1) ;;
  *) echo 'Unexpected host; stopping.'; exit 1 ;;
esac
# This is the original VM, so retain its machine-id and SSH host keys.
if ! test -e /etc/hosts.before-cs5488-worker1; then
  cp -a /etc/hosts /etc/hosts.before-cs5488-worker1
fi
hostnamectl set-hostname spark-worker-1
python3 - <<'PY'
from pathlib import Path
p = Path('/etc/hosts')
lines = p.read_text().splitlines()
found = False
for i, line in enumerate(lines):
    fields = line.split()
    if fields and fields[0] == '127.0.1.1':
        lines[i] = '127.0.1.1 spark-worker-1'
        found = True
if not found:
    lines.append('127.0.1.1 spark-worker-1')
p.write_text('\n'.join(lines) + '\n')
PY
hostnamectl --static
echo 'Worker 1 name updated. No reboot needed.'
