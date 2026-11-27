"""One source-date fragment, using the unchanged common Spark cleaner."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2] / "a_data_pipeline"))
from gharchive_a.spark_clean import clean_spark


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--raw-dir",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--master",required=True)
    args = parser.parse_args()
    clean_spark(json.loads(args.config.read_text(encoding="utf-8")),args.raw_dir,args.output,
                master=args.master,benchmark=True)


if __name__=="__main__":
    main()
