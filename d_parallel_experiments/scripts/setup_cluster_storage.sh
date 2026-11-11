#!/usr/bin/env bash
# Administrator setup only. Does not start Spark or execute experiments.
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Run with sudo.'; exit 1; }
node=$(hostnamectl --static)
case "$node" in
  spark-master) expected_ip=192.168.20.130 ;;
  spark-worker-1) expected_ip=192.168.20.129 ;;
  spark-worker-2) expected_ip=192.168.20.131 ;;
  *) echo "Unexpected hostname: $node"; exit 1 ;;
esac
ip -4 -o addr show dev ens33 | grep -Fq " $expected_ip/" || {
  echo 'IP differs from the agreed node inventory; stopping.'; exit 1;
}
test "$(id -u lishuo)" = 1000 && test "$(id -g lishuo)" = 1000 || {
  echo 'Unexpected UID/GID; review NFS permissions before continuing.'; exit 1;
}
apt-get update
if test "$node" = spark-master; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y nfs-kernel-server nfs-common
else
  DEBIAN_FRONTEND=noninteractive apt-get install -y nfs-common
fi

# Keep existing rules; allow TCP only from these dedicated cluster peers.
if command -v ufw >/dev/null; then
  for peer in 192.168.20.129 192.168.20.130 192.168.20.131; do
    if test "$peer" != "$expected_ip"; then
      ufw allow in on ens33 proto tcp from "$peer" to "$expected_ip" comment 'cs5488 cluster peer'
    fi
  done
fi

if ! test -e /etc/hosts.before-cs5488-cluster; then
  cp -a /etc/hosts /etc/hosts.before-cs5488-cluster
fi
python3 - <<'PY'
from pathlib import Path
p = Path('/etc/hosts')
names = {'spark-master', 'spark-worker-1', 'spark-worker-2'}
result = []
for line in p.read_text().splitlines():
    plain, sep, comment = line.partition('#')
    fields = plain.split()
    if fields and any(name in names for name in fields[1:]):
        aliases = [name for name in fields[1:] if name not in names]
        if aliases:
            result.append(fields[0] + ' ' + ' '.join(aliases) + (' #' + comment if sep else ''))
        continue
    result.append(line)
result.extend(['192.168.20.130 spark-master', '192.168.20.129 spark-worker-1',
               '192.168.20.131 spark-worker-2'])
p.write_text('\n'.join(result) + '\n')
PY

if test "$node" = spark-master; then
  if mountpoint -q /data/cs5488; then
    echo 'Unexpected existing mount at server export path; stopping.'; exit 1
  fi
  install -d -m 2770 -o lishuo -g lishuo /data/cs5488
  for sub in raw runs event-logs checks manifests; do
    install -d -m 2770 -o lishuo -g lishuo "/data/cs5488/$sub"
  done
  install -d /etc/exports.d
  export_file=/etc/exports.d/cs5488.exports
  if test -f "$export_file" && ! test -e "$export_file.before-cs5488"; then
    cp -a "$export_file" "$export_file.before-cs5488"
  fi
  printf '%s\n' '/data/cs5488 192.168.20.129(rw,sync,no_subtree_check,root_squash) 192.168.20.131(rw,sync,no_subtree_check,root_squash)' > "$export_file"
  systemctl enable --now nfs-kernel-server
  exportfs -ra
  runuser -u lishuo -- sh -c 'printf "cs5488-master-storage-v1\n" > /data/cs5488/checks/master-ready.txt'
  exportfs -v
else
  install -d -m 755 /data/cs5488
  if ! mountpoint -q /data/cs5488 && test -n "$(find /data/cs5488 -mindepth 1 -maxdepth 1 -print -quit)"; then
    echo 'Mount target contains local files; stopping to avoid hiding them.'; exit 1
  fi
  if ! test -e /etc/fstab.before-cs5488; then
    cp -a /etc/fstab /etc/fstab.before-cs5488
  fi
  python3 - <<'PY'
from pathlib import Path
p = Path('/etc/fstab')
source = '192.168.20.130:/data/cs5488'
for line in p.read_text().splitlines():
    f = line.split()
    if not f or f[0].startswith('#'):
        continue
    if len(f) > 1 and f[1] == '/data/cs5488':
        if f[0] != source or f[2] not in ('nfs', 'nfs4'):
            raise SystemExit('Conflicting fstab entry; stopping.')
        break
else:
    with p.open('a') as out:
        out.write('\n# CS5488 shared experiment storage\n')
        out.write(source + ' /data/cs5488 nfs vers=4.2,proto=tcp,hard,_netdev,nofail,x-systemd.mount-timeout=20s 0 0\n')
PY
  systemctl daemon-reload
  if ! mountpoint -q /data/cs5488; then
    timeout 45 mount /data/cs5488
  fi
  test "$(findmnt -n -o SOURCE --target /data/cs5488)" = '192.168.20.130:/data/cs5488' || {
    echo 'Unexpected mounted source; stopping.'; exit 1;
  }
  runuser -u lishuo -- cat /data/cs5488/checks/master-ready.txt
  runuser -u lishuo -- sh -c 'hostname > /data/cs5488/checks/"$(hostname)"-write-test.txt'
fi
echo "SETUP_OK $node"
echo 'No reboot required. Spark services have not been started by this script.'
