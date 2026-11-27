"""Summarize success, failure and resume attempts without summing parent spans."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2] / "a_data_pipeline"))
from gharchive_a.common import sha256_file, write_csv, write_json
from rolling_pipeline.batch_support import read_json, tree_bytes
from verify_results import read_run


def collect_timings(root):
    """Read recorded spans, including cleanup files outside the timing prefix."""
    root = Path(root)
    rows = []
    paths = set(root.rglob("timing*.json"))
    paths.update(root.glob("invocations/attempt-*/*_cleanup.json"))
    for path in sorted(paths):
        value = read_json(path)
        if "stage" in value and "elapsed_seconds" in value:
            rows.append(dict(path=path.relative_to(root).as_posix(),**value))
    return rows


def summarize(root):
    root = Path(root).resolve()
    run = read_json(root / "run.json")
    rows = collect_timings(root)
    columns = ["path","stage","batch","started_at","finished_at","elapsed_seconds","state","exit_code","is_parent","parent"]
    write_csv(root / "stage_timings.csv",columns,rows)
    result = {"state":run["state"],"run_id":run["run_id"],"identity":run["identity"],"host":run["host"],
              "timing_records":rows,"timing_note":"Parent batch/merge/invocation spans overlap their children; do not sum all rows. Cached verification is measured; skipped compute has no invented zero duration.",
              "retained_run_bytes":tree_bytes(root)}
    if run["state"]=="completed":
        _,folder,inputs,coverage = read_run(root)
        result.update(summary=read_json(folder / "summary.json"),coverage=coverage,
                      input_files=len(inputs),input_bytes=sum(r["bytes"] for r in inputs),final_output=str(folder))
    write_json(root / "run_summary.json",result)
    return result


def worker_evidence(root,event_logs,worker_hosts):
    """Require both requested hosts in successful TaskEnd events per application.

    Supports uncompressed, non-rolling Spark event logs, as configured in the
    documented D4 smoke command. Missing/end-incomplete logs fail explicitly.
    """
    if (len(worker_hosts)!=2 or any(not isinstance(host,str) or not host.strip() for host in worker_hosts)
            or len(set(worker_hosts))!=2):
        raise ValueError("Two-worker evidence requires two distinct nonempty worker hosts")
    run,_,_,_ = read_run(root)
    if not run["identity"]["spark"]["master"].startswith("spark://"):
        raise ValueError("Two-worker evidence requires a distributed Spark run")
    applications = []
    for batch in run["identity"]["plan"]["batches"]:
        accepted = read_json(Path(root) / "batches" / batch["id"] / "accepted.json")
        for fragment in accepted["fragments"]:
            app = read_json(Path(fragment["valid"]).parent / "application.json")["application_id"]
            event_file = Path(event_logs) / app
            hosts = Counter()
            completed = False
            application_id = None
            with event_file.open(encoding="utf-8") as handle:
                for line in handle:
                    event = json.loads(line)
                    if event["Event"]=="SparkListenerApplicationStart":
                        application_id = event["App ID"]
                    if event["Event"]=="SparkListenerApplicationEnd":
                        completed = True
                    if event["Event"]=="SparkListenerTaskEnd" and event.get("Task End Reason",{}).get("Reason")=="Success":
                        hosts[event["Task Info"]["Host"]]+=1
            passed = application_id==app and completed and all(hosts[h]>0 for h in worker_hosts)
            applications.append({"application_id":app,"log":str(event_file),"sha256":sha256_file(event_file),
                                 "successful_tasks_by_host":dict(hosts),"application_ended":completed,"passed":passed})
    result = {"passed":bool(applications) and all(a["passed"] for a in applications),
              "required_worker_hosts":worker_hosts,"applications":applications}
    write_json(Path(root) / "worker_evidence.json",result)
    if not result["passed"]:
        raise RuntimeError("Missing successful task participation or completed application logs")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir",type=Path,required=True)
    p.add_argument("--event-log-dir",type=Path)
    p.add_argument("--worker-hosts",nargs=2,help="Exact Host names from Spark task logs")
    args = p.parse_args()
    result = summarize(args.run_dir)
    if bool(args.event_log_dir)!=bool(args.worker_hosts):
        p.error("--event-log-dir and --worker-hosts must be supplied together")
    if args.event_log_dir:
        worker_evidence(args.run_dir,args.event_log_dir,args.worker_hosts)
    print(result["state"])


if __name__=="__main__":
    main()
