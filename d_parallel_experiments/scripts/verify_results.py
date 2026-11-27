"""Exact, multiplicity-aware comparison of two complete rolling run roots."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT / "a_data_pipeline"))
import pyarrow as pa
import pyarrow.dataset as ds
from gharchive_a.common import EVENT_COLUMNS, write_json
from rolling_pipeline.batch_support import read_json, timed
from rolling_pipeline.batch_merge import (CANDIDATE_COLUMNS, DAILY_COLUMNS, INTEGER_FIELDS,
    create_db, exact_difference, normalized, require_event_schema)
from run_batch_pipeline import verified_marker


def read_run(root):
    root = Path(root).resolve()
    run = read_json(root / "run.json")
    if run["state"]!="completed":
        raise ValueError("Run is not complete")
    identity = run["identity"]
    inputs = []
    for batch in identity["plan"]["batches"]:
        accepted = verified_marker(root,root / "batches" / batch["id"] / "accepted.json",identity)
        if accepted["batch"]!=batch:
            raise ValueError("Accepted batch differs from plan")
        inputs.extend(accepted["inputs"])
    final = verified_marker(root,root / "final_accepted.json",identity)
    folder = root / final["attempt"] / "result"
    expected_names = [n for b in identity["plan"]["batches"] for n in b["archives"]]
    coverage = read_json(folder / "coverage.json")
    if coverage["source_archives"]!=expected_names or coverage["missing_source_hours"] or coverage["verified_hours"]!=len(expected_names):
        raise ValueError("Final coverage does not match source plan")
    final_inputs = read_json(folder / "input_manifest.json")["archives"]
    if final_inputs != inputs:
        raise ValueError("Final inputs differ from accepted batch inputs")
    checks = read_json(folder / "summary.json")["checks"]
    if not checks or not all(v is True for v in checks.values()):
        raise ValueError("Final acceptance checks did not pass")
    return run,folder,inputs,coverage


def load_side(db,side,folder):
    dataset = ds.dataset(folder / "events_clean.parquet",format="parquet")
    require_event_schema(dataset.schema)
    fields = ",".join(k+(" INTEGER" if k in INTEGER_FIELDS else " TEXT") for k in EVENT_COLUMNS)
    db.execute(f"CREATE TABLE {side} ({fields})")
    for batch in dataset.to_batches(batch_size=10000):
        rows = [normalized(r) for r in batch.to_pylist()]
        db.executemany(f"INSERT INTO {side} VALUES ("+",".join("?" for _ in EVENT_COLUMNS)+")",
                       ([r[k] for k in EVENT_COLUMNS] for r in rows))
    db.execute(f"CREATE INDEX {side}_repo ON {side}(repo_id,event_time DESC,source_hour DESC,source_line DESC)")
    db.execute(f"CREATE TABLE {side}_daily (repo_id INTEGER,event_date TEXT,event_type TEXT,event_count INTEGER)")
    daily = ds.dataset(folder / "repo_daily_counts.parquet",format="parquet")
    if daily.schema.names!=DAILY_COLUMNS or [f.type for f in daily.schema]!=[pa.int64(),pa.date32(),pa.string(),pa.int64()]:
        raise ValueError("Daily field/type contract differs")
    for batch in daily.to_batches(batch_size=10000):
        db.executemany(f"INSERT INTO {side}_daily VALUES (?,?,?,?)",
                       ((r["repo_id"],r["event_date"].isoformat(),r["event_type"],r["event_count"]) for r in batch.to_pylist()))
    db.execute(f"CREATE VIEW {side}_recount AS SELECT repo_id,event_date,event_type,COUNT(*) AS event_count FROM {side} GROUP BY repo_id,event_date,event_type")
    db.execute(f"CREATE TABLE {side}_candidates (repo_id INTEGER,repo_name TEXT,first_observed_at TEXT,last_observed_at TEXT,event_count INTEGER,observed_name_count INTEGER)")
    with (folder / "repo_candidates.csv").open(encoding="utf-8",newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames!=CANDIDATE_COLUMNS:
            raise ValueError("Candidate columns differ")
        def candidate_rows():
            for row in reader:
                yield [int(row[k]) if k in ("repo_id","event_count","observed_name_count") else (row[k] or None) for k in CANDIDATE_COLUMNS]
        db.executemany(f"INSERT INTO {side}_candidates VALUES (?,?,?,?,?,?)",candidate_rows())
    db.execute(f"""CREATE VIEW {side}_recandidates AS SELECT c.repo_id,
      (SELECT n.repo_name FROM {side} n WHERE n.repo_id=c.repo_id AND n.repo_name IS NOT NULL
       ORDER BY n.event_time DESC,n.source_hour DESC,n.source_line DESC LIMIT 1) AS repo_name,
      MIN(c.event_time) AS first_observed_at,MAX(c.event_time) AS last_observed_at,
      COUNT(*) AS event_count,COUNT(DISTINCT c.repo_name) AS observed_name_count FROM {side} c GROUP BY c.repo_id""")
    count,unique = db.execute(f"SELECT COUNT(*),COUNT(DISTINCT event_id) FROM {side}").fetchone()
    checks = {side+"_unique_ids": count==unique,
              side+"_daily_matches_events":exact_difference(db,side+"_daily",side+"_recount",DAILY_COLUMNS)==[0,0],
              side+"_candidates_match_events":exact_difference(db,side+"_candidates",side+"_recandidates",CANDIDATE_COLUMNS)==[0,0]}
    # Reuse original full CSV/Parquet checks; final exports obey the same contract.
    from gharchive_a.compare import check_parquet
    import gzip
    db.execute("CREATE TABLE "+side+"_events ("+",".join(k+" TEXT" for k in EVENT_COLUMNS)+")")
    with gzip.open(folder / "events_clean.csv.gz","rt",encoding="utf-8",newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames!=EVENT_COLUMNS:
            raise ValueError("Event CSV columns differ")
        db.executemany(f"INSERT INTO {side}_events VALUES ("+",".join("?" for _ in EVENT_COLUMNS)+")",([r[k] for k in EVENT_COLUMNS] for r in reader))
    checks[side+"_csv_parquet"] = check_parquet(db,side,folder)["matches_csv"]
    db.execute(f"CREATE TABLE {side}_csv_daily (repo_id INTEGER,event_date TEXT,event_type TEXT,event_count INTEGER)")
    with (folder / "repo_daily_counts.csv").open(encoding="utf-8",newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames!=DAILY_COLUMNS:
            raise ValueError("Daily CSV columns differ")
        db.executemany(f"INSERT INTO {side}_csv_daily VALUES (?,?,?,?)",((int(r["repo_id"]),r["event_date"],r["event_type"],int(r["event_count"])) for r in reader))
    checks[side+"_daily_csv_parquet"] = exact_difference(db,side+"_daily",side+"_csv_daily",DAILY_COLUMNS)==[0,0]
    for label in ("conflicts","duplicates"):
        table = side+"_"+label
        db.execute("CREATE TABLE "+table+" (event_id TEXT,canonical_sha256 TEXT,source_hour TEXT,source_line INTEGER,reason TEXT)")
        with (folder / (label+".csv")).open(encoding="utf-8",newline="") as handle:
            db.executemany("INSERT INTO "+table+" VALUES (?,?,?,?,?)",
                           ((r["event_id"],r["canonical_sha256"],r["source_hour"],int(r["source_line"]),r["reason"]) for r in csv.DictReader(handle)))
    return checks,count


def compare_runs(left,right,output):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False)
    report = {"passed":False,"state":"running","left":str(left),"right":str(right),"checks":{}}
    db = create_db(output / "comparison.sqlite3")
    try:
        with timed(output / "timing.json","exact_result_comparison"):
            lr,lf,li,lc = read_run(left)
            rr,rf,ri,rc = read_run(right)
            signature = lambda items: [(r["name"],r["bytes"],r["sha256"]) for r in items]
            report["checks"]["same_inputs"] = signature(li)==signature(ri)
            report["checks"]["same_coverage"] = lc==rc
            report["checks"]["same_rules"] = lr["identity"]["code"]["rule_version"]==rr["identity"]["code"]["rule_version"]
            report["checks"]["same_adjudication_counts"] = read_json(lf / "summary.json")["counts"]==read_json(rf / "summary.json")["counts"]
            for side,folder in (("left",lf),("right",rf)):
                checks,count = load_side(db,side,folder)
                report["checks"].update(checks)
                report[side+"_events"] = count
            report["differences"] = {}
            for label,a,b,columns in (("events","left","right",EVENT_COLUMNS),
                                     ("daily","left_daily","right_daily",DAILY_COLUMNS),
                                     ("candidates","left_candidates","right_candidates",CANDIDATE_COLUMNS),
                                     ("conflicts","left_conflicts","right_conflicts",["event_id","canonical_sha256","source_hour","source_line","reason"]),
                                     ("duplicates","left_duplicates","right_duplicates",["event_id","canonical_sha256","source_hour","source_line","reason"])):
                counts = exact_difference(db,a,b,columns)
                report["differences"][label] = {"left_only":counts[0],"right_only":counts[1]}
                report["checks"][label+"_equal_with_multiplicity"] = counts==[0,0]
                cols = ",".join(columns)
                for suffix,x,y in (("left_only",a,b),("right_only",b,a)):
                    rows = db.execute(f"SELECT {cols},COUNT(*) AS multiplicity FROM {x} GROUP BY {cols} EXCEPT SELECT {cols},COUNT(*) FROM {y} GROUP BY {cols} LIMIT 20").fetchall()
                    write_json(output / f"{label}_{suffix}_examples.json",[dict(r) for r in rows])
            report["passed"] = all(report["checks"].values())
            report["state"] = "completed"
            db.commit()
    except BaseException as error:
        report.update(state="error",error=f"{type(error).__name__}: {error}")
        raise
    finally:
        db.close()
        write_json(output / "comparison_summary.json",report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left",type=Path,required=True,help="Complete rolling run root")
    parser.add_argument("--right",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True,help="New comparison directory")
    args = parser.parse_args(argv)
    try:
        report = compare_runs(args.left,args.right,args.output)
        print(json.dumps({"passed":report["passed"],"differences":report["differences"]}))
        return 0 if report["passed"] else 1
    except Exception as error:
        print(f"Comparison failed: {error}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
