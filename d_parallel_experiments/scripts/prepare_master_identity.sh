#!/usr/bin/env bash
# Run once from the VMware console, then reboot this cloned VM.
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Run with sudo.'; exit 1; }
test "$(hostnamectl --static)" = spark-master || { echo 'Expected spark-master; stopping.'; exit 1; }
marker=/var/lib/cs5488/master-identity-prepared
if test -f "$marker"; then
  echo 'Already prepared. Reboot if not yet done.'
  ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
  exit 0
fi
test "$(readlink -f /var/lib/dbus/machine-id)" = /etc/machine-id || {
  echo 'Unexpected D-Bus machine-id layout; stopping.'; exit 1;
}
umask 077
backup=$(mktemp -d /root/cs5488-master-identity.XXXXXXXX)
cp -a /etc/hosts /etc/machine-id "$backup/"
mkdir -p "$backup/old-ssh" "$backup/new/etc/ssh"
cp -a /etc/ssh/ssh_host_* "$backup/old-ssh/"
# Generate replacements before installing them; preserve user authorized_keys.
ssh-keygen -A -f "$backup/new"
systemd-id128 new > "$backup/new-machine-id"
grep -Eq '^[0-9a-f]{32}$' "$backup/new-machine-id"
for key in "$backup"/new/etc/ssh/ssh_host_*_key; do
  install -m 600 "$key" "/etc/ssh/$(basename "$key")"
  install -m 644 "$key.pub" "/etc/ssh/$(basename "$key").pub"
done
/usr/sbin/sshd -t
python3 - <<'PY'
from pathlib import Path
path = Path('/etc/hosts')
lines = path.read_text().splitlines()
result = []
found = False
for line in lines:
    fields = line.split()
    if fields and fields[0] == '127.0.1.1':
        line = '127.0.1.1 spark-master'
        found = True
    result.append(line)
if not found:
    result.append('127.0.1.1 spark-master')
path.write_text('\n'.join(result) + '\n')
PY
install -m 444 "$backup/new-machine-id" /etc/machine-id
mkdir -p /var/lib/cs5488
printf '%s\n' "$backup" > "$marker"
echo "Backup: $backup"
echo 'New SSH fingerprint (send this public fingerprint after reboot):'
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
echo 'Prepared successfully. Now run: sudo reboot'
