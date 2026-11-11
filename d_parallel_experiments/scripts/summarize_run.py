"""Post-run evidence, outside benchmark timing: tasks and output fingerprints."""
import csv
import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
import pyarrow.dataset as ds

run = Path('/data/cs5488/runs') / sys.argv[1]
app = json.loads((run/'application.json').read_text())['application_id']
event = Path('/data/cs5488/event-logs') / app
hosts = Counter()
metrics = Counter()
executors = {}
with event.open() as f:
    for line in f:
        e=json.loads(line)
        if e['Event']=='SparkListenerExecutorAdded':
            executors[e['Executor ID']]=e['Executor Info']
        if e['Event']=='SparkListenerTaskEnd':
            if e.get('Task End Reason',{}).get('Reason')=='Success':
                hosts[e['Task Info']['Host']]+=1
            m=e.get('Task Metrics',{})
            for k in ('Executor Run Time','JVM GC Time','Memory Bytes Spilled','Disk Bytes Spilled'):
                metrics[k]+=m.get(k,0)
            metrics['Shuffle Write Bytes']+=m.get('Shuffle Write Metrics',{}).get('Shuffle Bytes Written',0)
            r=m.get('Shuffle Read Metrics',{})
            metrics['Shuffle Read Bytes']+=r.get('Remote Bytes Read',0)+r.get('Local Bytes Read',0)

def digest(path, zipped=False):
    h=hashlib.sha256()
    with (gzip.open(path,'rb') if zipped else path.open('rb')) as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

fingerprints={}
for name in ('events_clean.csv.gz','repo_daily_counts.csv','repo_candidates.csv','repo_name_history.csv'):
    fingerprints[name]=digest(run/name,name.endswith('.gz'))
# Order-independent complete row fingerprint, preserving multiplicities.
data=ds.dataset(run/'events_clean.parquet',format='parquet')
acc=0
count=0
for batch in data.to_batches(batch_size=10000):
    for row in batch.to_pylist():
        h=hashlib.sha256(json.dumps(row,sort_keys=True,default=str,ensure_ascii=False).encode()).digest()
        acc=(acc+int.from_bytes(h,'big')) % (1<<256)
        count+=1
quality=json.loads((run/'quality_summary.json').read_text())
result=dict(run_id=run.name,application_id=app,event_log=str(event),executors=executors,
            successful_tasks_by_host=dict(hosts),task_metrics=dict(metrics),
            fingerprints=fingerprints,parquet_multiset_sha256_sum=f'{acc:064x}',
            parquet_rows=count,parquet_schema=str(data.schema),
            quality_checks=quality['checks'],cleaned_events=quality['cleaned_events'])
assert all(quality['checks'].values()) and count==quality['cleaned_events']
(Path('/data/cs5488/measurements')/(run.name+'_evidence.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('run_id','successful_tasks_by_host','parquet_rows')}))
