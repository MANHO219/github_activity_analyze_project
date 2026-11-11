#!/usr/bin/env bash
# User-level preparation ONLY. Does not launch Java, Spark services, or jobs.
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
target=/home/lishuo/cs5488-cluster
test "$(id -un)" = lishuo || { echo 'Run as lishuo without sudo.'; exit 1; }
test -f "$source_dir/configs/spark-env.sh"
test -f "$source_dir/configs/spark-defaults.conf"
case "$(hostname -s)" in
  spark-master) node_ip=192.168.20.130 ;;
  spark-worker-1) node_ip=192.168.20.129 ;;
  spark-worker-2) node_ip=192.168.20.131 ;;
  *) echo 'Unknown node'; exit 1 ;;
esac
ip -4 -o addr show | grep -Fq " $node_ip/" || { echo 'Node IP changed'; exit 1; }
test "$(cat /data/cs5488/checks/master-ready.txt)" = cs5488-master-storage-v1
mkdir -p "$target"/{conf,bin,logs,pids,worker-work,local,backups}
backup_dir="$target/backups/$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$backup_dir"
for name in spark-env.sh spark-defaults.conf; do
  if test -f "$target/conf/$name"; then cp -p "$target/conf/$name" "$backup_dir/"; fi
  install -m 644 "$source_dir/configs/$name" "$target/conf/$name"
done
printf '\nspark.driver.host %s\n' "$node_ip" >> "$target/conf/spark-defaults.conf"
if test -f "$target/bin/cluster_service.sh"; then cp -p "$target/bin/cluster_service.sh" "$backup_dir/"; fi
install -m 755 "$source_dir/scripts/cluster_service.sh" "$target/bin/cluster_service.sh"
bash -n "$target/conf/spark-env.sh"
bash -n "$target/bin/cluster_service.sh"
echo "CONFIGURED $(hostname -s) — services NOT started"
"$target/bin/cluster_service.sh" check
