from pathlib import Path
import tarfile,hashlib,json
base=Path('/data/cs5488/runs/python_6h_reconcile_20261111_01')
status=json.loads((base/'reconciliation_status.json').read_text())
assert status['state']=='completed',status
import gzip
spark=Path('/data/cs5488/runs/d4stable_6h_r1')
expected=json.loads(Path('/data/cs5488/measurements/d4stable_6h_r1_evidence.json').read_text())['fingerprints']
observed={}
for name in expected:
 h=hashlib.sha256()
 with (gzip.open(spark/name,'rb') if name.endswith('.gz') else (spark/name).open('rb')) as stream:
  for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
 observed[name]=h.hexdigest()
assert observed==expected,'Spark output changed since six-hour measurements'
(base/'spark_fingerprint_reverification.json').write_text(json.dumps({'passed':True,'fingerprints':observed},indent=2)+'\n')
archive=Path('/data/cs5488/python_spark_6h_reconciliation_20261111.tar.gz')
with tarfile.open(archive,'x:gz') as tar:
 for file in base.glob('*'):
  if file.is_file() and file.suffix=='.json':tar.add(file,arcname=file.name)
 for folder in ['python','original_comparison','field_comparison']:
  for file in (base/folder).iterdir():
   if file.is_file() and (file.suffix=='.json' or file.name.endswith('_examples.csv')):
    tar.add(file,arcname=folder+'/'+file.name)
 for file in Path('/data/cs5488/reconciliation_tools_20261111').iterdir():
  if file.is_file():tar.add(file,arcname='execution/'+file.name)
with archive.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
print(json.dumps({'archive':str(archive),'sha256':sha,'status':status},indent=2))
