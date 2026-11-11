#!/usr/bin/env bash
set -euo pipefail
source /home/lishuo/cs5488-cluster/conf/spark-env.sh
mode=$1
root=/data/cs5488/project/d_parallel_experiments/scripts
for repeat in warmup r1 r2 r3; do
  runid="${mode,,}_6h_${repeat}"
  bash "$root/submit_run.sh" "$mode" 6 "$runid"
  python "$root/summarize_run.py" "$runid"
done
