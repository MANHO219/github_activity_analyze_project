#!/usr/bin/env bash
set -euo pipefail
source /home/lishuo/cs5488-cluster/conf/spark-env.sh
mode=$1
hours=$2
runid=$3
root=/data/cs5488/project
out=/data/cs5488/runs/$runid
test ! -e "$out"
mkdir -p /data/cs5488/measurements
python - "$runid" <<'PY'
import hashlib,json,os,platform,socket,sys
from pathlib import Path
root=Path('/data/cs5488/project')
files=list((root/'a_data_pipeline/gharchive_a').glob('*.py'))+list((root/'d_parallel_experiments/scripts').glob('*.py'))
record=dict(host=socket.gethostname(),cpu_count=os.cpu_count(),platform=platform.platform(),
            meminfo=Path('/proc/meminfo').read_text(),loadavg=Path('/proc/loadavg').read_text(),
            source_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)})
Path('/data/cs5488/measurements',sys.argv[1]+'_environment.json').write_text(json.dumps(record,indent=2)+'\n')
PY
if [ "$mode" = D4 ]; then
  master=spark://192.168.20.130:7077
  memory=2g
else
  master="local[${mode#L}]"
  memory=4g
fi
start=$(date +%s.%N)
set +e
"$SPARK_HOME/bin/spark-submit" --master "$master" --deploy-mode client \
  --driver-memory "$memory" --conf "spark.driver.host=$SPARK_LOCAL_IP" \
  --conf spark.sql.shuffle.partitions=12 --conf spark.sql.adaptive.enabled=false \
  "$root/d_parallel_experiments/scripts/run_experiment.py" \
  --master "$master" --hours "$hours" --output "$out" \
  > "/data/cs5488/measurements/$runid.log" 2>&1
status=$?
end=$(date +%s.%N)
python - "$runid" "$mode" "$hours" "$start" "$end" "$status" <<'PY'
import json,sys
from pathlib import Path
run,mode,hours,start,end,status=sys.argv[1:]
d=dict(run_id=run,mode=mode,hours=int(hours),start_epoch=float(start),end_epoch=float(end),elapsed_seconds=float(end)-float(start),exit_code=int(status),warmup='warmup' in run)
Path('/data/cs5488/measurements',run+'.json').write_text(json.dumps(d,indent=2)+'\n')
print(json.dumps(d))
PY
exit "$status"
