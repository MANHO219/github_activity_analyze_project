#!/usr/bin/env bash
set -euo pipefail
root=/data/cs5488/project/d_parallel_experiments/scripts
for repeat in warmup r1 r2 r3; do
  runid="d4stable_6h_$repeat"
  bash "$root/submit_run.sh" D4 6 "$runid"
  /home/lishuo/cs5488-round1/env/bin/python "$root/summarize_run.py" "$runid"
done
