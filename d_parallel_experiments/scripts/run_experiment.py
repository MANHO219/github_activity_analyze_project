"""One Spark run; resource settings are supplied by spark-submit."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'a_data_pipeline'))
from gharchive_a.spark_clean import clean_spark

p = argparse.ArgumentParser()
p.add_argument('--hours', type=int, required=True)
p.add_argument('--master', required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
cfg = json.loads((ROOT / 'a_data_pipeline/config/sample.json').read_text())
cfg['hours'] = list(range(a.hours))
clean_spark(cfg, Path('/data/cs5488/raw'), a.output, master=a.master, benchmark=True)
