import hashlib,json,sys,time,traceback
from pathlib import Path
from types import SimpleNamespace
root=Path('/data/cs5488/project');sys.path.insert(0,str(root/'a_data_pipeline'))
from gharchive_a.clean import clean
from gharchive_a.compare import compare
from compare_python_slice import run
base=Path('/data/cs5488/runs/python_6h_reconcile_20261111_01');base.mkdir(exist_ok=False)
status={'state':'running','reference_origin':'Python recomputed from same six raw archives; not teammate full-day output','spark_run':'d4stable_6h_r1'}
def save(): (base/'reconciliation_status.json').write_text(json.dumps(status,indent=2)+'\n')
save()
try:
 expected=json.loads(Path(__file__).with_name('expected_code.json').read_text())
 actual={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in expected}
 assert actual==expected,'deployed source mismatch'
 (base/'code_sha256.json').write_text(json.dumps(actual,indent=2)+'\n')
 manifest=json.loads((root/'a_data_pipeline/verification/20240115_1day/input_slices.json').read_text())
 checks=[]
 for rec in manifest['groups']['6h']['archives']:
  p=Path('/data/cs5488/raw')/rec['name']
  with p.open('rb') as f: sha=hashlib.file_digest(f,'sha256').hexdigest()
  assert sha==rec['sha256'] and p.stat().st_size==rec['bytes'],str(p)
  checks.append(dict(name=p.name,sha256=sha,bytes=p.stat().st_size))
 (base/'input_hash_verification.json').write_text(json.dumps(checks,indent=2)+'\n')
 cfg=json.loads((root/'a_data_pipeline/config/sample.json').read_text());cfg['hours']=list(range(6))
 start=time.time();print('PYTHON_CLEAN_START',flush=True)
 q=clean(cfg,Path('/data/cs5488/raw'),base/'python')
 status.update(python_elapsed_seconds=time.time()-start,python_events=q['cleaned_events']);save()
 print('PYTHON_CLEAN_DONE',status,flush=True)
 spark=Path('/data/cs5488/runs/d4stable_6h_r1')
 try:
  result=compare(base/'python',spark,base/'original_comparison')
  status['original_comparison_passed']=result['passed']
 except Exception as exc:
  status['original_comparison_error']=str(exc)
 save();print('ORIGINAL_COMPARISON_DONE',flush=True)
 result=run(SimpleNamespace(output=str(base/'field_comparison'),python_parquet=str(base/'python/events_clean.parquet'),spark_parquet=str(spark/'events_clean.parquet'),spark_daily=str(spark/'repo_daily_counts.csv'),source_files=[r['name'] for r in checks],expected_rows=1177282))
 status.update(field_comparison_passed=result['passed'],state='completed');save()
 print(json.dumps(status),flush=True)
except Exception as exc:
 status.update(state='error',error=str(exc));save();traceback.print_exc();raise
