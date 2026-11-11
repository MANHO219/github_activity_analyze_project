"""Archive small evidence and event logs, not raw data or output datasets."""
import tarfile
import sys
from pathlib import Path
base=Path('/data/cs5488')
target=base/(sys.argv[1] if len(sys.argv)>1 else 'experiment_evidence_20261110.tar.gz')
if target.exists():
    raise FileExistsError(f'Refusing to overwrite archive: {target}')
with tarfile.open(target,'w:gz') as archive:
    archive.add(base/'measurements',arcname='measurements')
    archive.add(base/'event-logs',arcname='event-logs')
    archive.add(base/'project/a_data_pipeline/verification/20240115_1day/input_slices.json',arcname='input_slices.json')
    for folder in (base/'runs').iterdir():
        for name in ('stage_status.json','input_manifest.json','quality_summary.json','effective_spark_config.json','application.json','spark_environment.json','download_manifest.json'):
            p=folder/name
            if p.exists():archive.add(p,arcname=str(Path('runs')/folder.name/name))
print(target)
