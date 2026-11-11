"""Download only the selected input slice and verify every published digest."""
import hashlib
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'a_data_pipeline'))
from gharchive_a.download import download
cfg = json.loads((ROOT / 'a_data_pipeline/config/sample.json').read_text())
hours = int(sys.argv[1])
cfg['hours'] = list(range(hours))
manifest = json.loads((ROOT / 'a_data_pipeline/verification/20240115_1day/input_slices.json').read_text())
download(cfg, Path('/data/cs5488/raw'), Path(sys.argv[2]), False)
for row in manifest['groups'][f'{hours}h']['archives']:
    path = Path('/data/cs5488/raw') / row['name']
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    assert path.stat().st_size == row['bytes'] and digest == row['sha256'], row['name']
print('ALL_INPUT_HASHES_VERIFIED', flush=True)
