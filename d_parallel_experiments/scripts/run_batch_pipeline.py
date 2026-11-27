"""UTC [start,end) rolling runner; plan-only never creates directories or jobs."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT / "a_data_pipeline"))
from gharchive_a.clean import clean
from gharchive_a.common import environment, sha256_file, utc_now, write_json
from rolling_pipeline.batch_download import download
from gharchive_a.inspect import inspect
from rolling_pipeline.batch_support import (GIB, check_space, cleanup_raw, code_identity, exclusive_lock,
    fragments, host_record, inventory, make_plan, monitor_space, new_attempt, read_json, safe_raw, timed, verify_inventory)
from rolling_pipeline.batch_merge import merge_outputs, python_valid_index, validate_fragment

CONFIGS = PROJECT / "d_parallel_experiments/configs"
ALIASES = {"L1":"local_1core.json","L4":"local_4core.json","D4":"distributed_4core.json"}


def load_spark(value, master=None, overrides=()):
    path = CONFIGS / ALIASES[value] if value in ALIASES else Path(value)
    cfg = read_json(path)
    if master:
        cfg["master"] = master
    allowed = {"name","master","driver_memory","conf"}
    if set(cfg) != allowed or not isinstance(cfg["conf"],dict):
        raise ValueError("Spark config requires name, master, driver_memory and conf")
    for option in overrides:
        key,sep,value = option.partition("=")
        if not sep or not key.startswith("spark.") or key in ("spark.master","spark.driver.memory"):
            raise ValueError("Use --spark-conf spark.key=value; master/memory belong in the configuration")
        cfg["conf"][key] = value
    if not (cfg["master"].startswith("local[") or cfg["master"].startswith("spark://")):
        raise ValueError("Spark master must be local[n] or spark://host:port")
    if cfg["master"].startswith("spark://") and "${" in cfg["master"]:
        raise ValueError("D4 requires --spark-master spark://<actual-master>:7077")
    if cfg["conf"].get("spark.sql.session.timeZone") != "UTC" or cfg["conf"].get("spark.sql.parquet.outputTimestampType") != "TIMESTAMP_MICROS":
        raise ValueError("UTC and TIMESTAMP_MICROS are required")
    return cfg


def spark_command(args, config, cfg_path, output):
    command = [args.spark_submit,"--master",config["master"],"--deploy-mode","client",
               "--driver-memory",config["driver_memory"]]
    for key,value in sorted(config["conf"].items()):
        command += ["--conf",f"{key}={value}"]
    command += [str(Path(__file__).with_name("spark_batch_job.py")),"--config",str(cfg_path),
                "--raw-dir",str(args.raw_dir),"--output",str(output),"--master",config["master"]]
    return command


def run_spark(command, log, guard):
    with Path(log).open("w",encoding="utf-8") as handle:
        process = subprocess.Popen(command,stdout=handle,stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                guard()
                time.sleep(0.5)
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode,command)
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise


def verified_marker(root, marker, identity):
    value = read_json(marker)
    if value["identity"] != identity:
        raise RuntimeError("Accepted output identity differs")
    attempt = (root / value["attempt"]).resolve()
    if not attempt.is_relative_to(root.resolve()) or attempt == root.resolve():
        raise RuntimeError("Accepted output path escapes run root")
    verify_inventory(attempt,value["retained_files"])
    return value


def acquire_inputs(args, batch, attempt, cfg, run, guard):
    registry_path = args.output_dir / "inputs.json"
    registry = read_json(registry_path) if registry_path.exists() else {}
    # Recover verified downloads even if interrupted before the registry write.
    for manifest in sorted((args.output_dir / "batches").glob("*/attempt-*/fragments/*/download-*/download_manifest.json")):
        for row in read_json(manifest).get("files",[]):
            if row.get("status") in ("downloaded_verified","cached_verified"):
                prior = registry.get(row["name"])
                if prior and (prior["bytes"],prior["sha256"]) != (row["bytes"],row["sha256"]):
                    raise RuntimeError("Input fingerprints differ across attempts")
                if not prior:
                    registry[row["name"]] = {k:row[k] for k in ("name","url","bytes","sha256")}
                if row["status"]=="downloaded_verified":
                    registry[row["name"]]["owner_run"] = run["run_id"]
    for name in batch["archives"]:
        path = safe_raw(args.raw_dir,name)
        if path.exists() and name in registry:
            row = registry[name]
            if path.stat().st_size != row["bytes"] or sha256_file(path)!=row["sha256"]:
                raise RuntimeError(f"Previously verified input changed: {path}")
    outputs = []
    for fragment_cfg in fragments(batch,cfg):
        folder = attempt / "fragments" / fragment_cfg["date"]
        folder.mkdir(parents=True)
        write_json(folder / "config.json",fragment_cfg)
        with timed(folder / "timing_download.json","download_verify",batch=batch["id"]):
            result = download(fragment_cfg,args.raw_dir,folder / ("download-"+run["run_id"]+"-"+attempt.name+"-"+fragment_cfg["date"]),guard)
            for row in result["files"]:
                previous = registry.get(row["name"])
                if previous and (previous["bytes"],previous["sha256"]) != (row["bytes"],row["sha256"]):
                    raise RuntimeError("Re-downloaded input differs from preserved fingerprint")
                value = {k:row[k] for k in ("name","url","bytes","sha256")}
                value["cache_status"] = row["status"]
                value["owner_run"] = run["run_id"] if row["status"]=="downloaded_verified" else (previous or {}).get("owner_run")
                registry[row["name"]] = value
            write_json(registry_path,registry)
            guard()
        outputs.append((fragment_cfg,folder))
    return outputs,[registry[name] for name in batch["archives"]]


def process_batch(args,batch,cfg,spark,run,identity):
    folder = args.output_dir / "batches" / batch["id"]
    folder.mkdir(parents=True,exist_ok=True)
    marker = folder / "accepted.json"
    if marker.exists():
        result = verified_marker(args.output_dir,marker,identity)
        if result.get("state")!="accepted" or result.get("batch")!=batch:
            raise RuntimeError("Accepted batch state/plan differs")
        print(f"{batch['id']}: accepted artifacts reverified; skipping compute",flush=True)
        return result
    attempt = new_attempt(folder)
    state = {"state":"planned","batch":batch,"attempt":str(attempt.relative_to(args.output_dir))}
    state_path = folder / "state.json"
    write_json(state_path,state)
    guard = lambda: check_space(args.raw_dir,args.output_dir,args.min_free_gib*GIB,attempt,args.batch_budget_gib*GIB)
    try:
        with timed(attempt / "timing_batch.json","batch_total",batch=batch["id"],is_parent=True), monitor_space(
                args.raw_dir,args.output_dir,attempt,args.min_free_gib*GIB,args.batch_budget_gib*GIB):
            outputs,inputs = acquire_inputs(args,batch,attempt,cfg,run,guard)
            state.update(state="input_verified")
            write_json(state_path,state)
            retained_fragments = []
            for fragment_cfg,fragment in outputs:
                with timed(fragment / "timing_inspection.json","raw_inspection",batch=batch["id"]):
                    inspect(fragment_cfg,args.raw_dir,fragment / "inspection")
                    guard()
                command = spark_command(args,spark,fragment / "config.json",fragment / "clean") if args.engine=="spark" else None
                with timed(fragment / "timing_clean.json",args.engine+"_clean_export",batch=batch["id"],command=command) as timing:
                    if args.engine=="spark":
                        run_spark(command,fragment / "spark.log",guard)
                        effective = read_json(fragment / "clean/effective_spark_config.json")
                        required = dict(spark["conf"], **{"spark.master":spark["master"],"spark.driver.memory":spark["driver_memory"]})
                        if any(str(effective.get(k)).lower()!=str(v).lower() for k,v in required.items()):
                            raise RuntimeError("Spark effective config does not match requested config")
                        timing["effective_config"] = effective
                    else:
                        clean(fragment_cfg,args.raw_dir,fragment / "clean")
                        python_valid_index(fragment / "clean")
                    guard()
                retained_fragments.append({"batch":batch["id"],"fragment":fragment_cfg["date"],
                                           "valid":str((fragment / "clean/valid_before_dedup.parquet").resolve())})
            state.update(state="processed")
            write_json(state_path,state)
            with timed(attempt / "timing_accept.json","batch_acceptance",batch=batch["id"]):
                for fragment_cfg,fragment in outputs:
                    expected = {r["name"]:(r["bytes"],r["sha256"]) for r in inputs if r["name"].startswith(fragment_cfg["date"]+"-")}
                    for stage in ("inspection","clean"):
                        manifest = read_json(fragment / stage / "input_manifest.json")
                        observed = {r["name"]:(r["bytes"],r["sha256"]) for r in manifest["observed_files"]}
                        if observed!=expected or manifest["missing_files"]:
                            raise RuntimeError("Input snapshots/coverage differ between stages")
                    inspection = read_json(fragment / "inspection/inspection_summary.json")
                    quality = read_json(fragment / "clean/quality_summary.json")
                    if inspection["line_status_counts"] != quality["line_status_counts"]:
                        raise RuntimeError("Inspection/cleaning line counts differ")
                    report = validate_fragment(fragment / "clean",fragment / "acceptance.sqlite3",guard)
                    write_json(fragment / "acceptance.json",report)
                guard()
        result = {"state":"accepted","identity":identity,"batch":batch,"inputs":inputs,
                  "attempt":str(attempt.relative_to(args.output_dir)),"fragments":retained_fragments,
                  "retained_files":inventory(attempt)}
        write_json(marker,result)
        state.update(state="accepted")
        write_json(state_path,state)
        return result
    except BaseException as error:
        state.update(state="error",failed_stage=state["state"],error=f"{type(error).__name__}: {error}")
        write_json(state_path,state)
        raise


def execute(args,plan,spark):
    args.raw_dir = args.raw_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    if args.raw_dir==args.output_dir or args.raw_dir.is_relative_to(args.output_dir) or args.output_dir.is_relative_to(args.raw_dir):
        raise ValueError("Raw and output roots must be disjoint")
    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not (args.output_dir / "run.json").is_file():
        raise RuntimeError("Nonempty output directory has no compatible run identity")
    args.raw_dir.mkdir(parents=True,exist_ok=True)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    with exclusive_lock(args.output_dir / ".batch.lock"),exclusive_lock(args.raw_dir / ".batch.lock"):
        cfg = read_json(PROJECT / "a_data_pipeline/config/sample.json")
        cfg["base_url"] = args.base_url
        identity = {"format":"rolling-v1","plan":plan,"raw_dir":str(args.raw_dir),"spark":spark,
                    "engine":args.engine,"cleanup":args.cleanup,"code":code_identity(),"input_config":cfg,
                    "budgets":{"min_free_gib":args.min_free_gib,"batch_budget_gib":args.batch_budget_gib,
                               "merge_budget_gib":args.merge_budget_gib,"sqlite_cache_mib":args.sqlite_cache_mib},
                    "spark_submit":args.spark_submit}
        run_path = args.output_dir / "run.json"
        if run_path.exists():
            run = read_json(run_path)
            if run["identity"]!=identity:
                raise RuntimeError("Incompatible parameters/code/rules; use a new output directory")
        else:
            run = {"run_id":uuid.uuid4().hex,"identity":identity,"state":"planned","host":host_record(),"environment":environment()}
            write_json(run_path,run)
        if args.cleanup=="accepted-raw":
            owner = args.raw_dir / ".batch-owner.json"
            if owner.exists():
                if read_json(owner)["run_id"]!=run["run_id"]:
                    raise RuntimeError("Raw root is owned by a different run; use retain")
            elif any(p.name!=".batch.lock" for p in args.raw_dir.iterdir()):
                raise RuntimeError("accepted-raw requires a NEW empty dedicated raw directory; existing caches use retain")
            else:
                write_json(owner,{"run_id":run["run_id"],"output":str(args.output_dir)})
        invocation = new_attempt(args.output_dir / "invocations")
        try:
            with timed(invocation / "timing.json","invocation",is_parent=True):
                run.update(state="running",started_at=utc_now())
                write_json(run_path,run)
                accepted = []
                for batch in plan["batches"]:
                    info = process_batch(args,batch,cfg,spark,run,identity)
                    accepted.append(info)
                    if args.cleanup=="accepted-raw":
                        folder = args.output_dir / "batches" / batch["id"]
                        with timed(invocation / (batch["id"]+"_cleanup.json"),"raw_cleanup",batch=batch["id"]):
                            # Acceptance was reverified above, even after a previous deletion.
                            cleanup_raw(args.raw_dir,folder,info,run["run_id"])
                            write_json(folder / "state.json",{"state":"raw_cleaned","batch":batch})
                final_marker = args.output_dir / "final_accepted.json"
                if final_marker.exists():
                    final = verified_marker(args.output_dir,final_marker,identity)
                else:
                    attempt = new_attempt(args.output_dir / "merge")
                    guard = lambda: check_space(args.raw_dir,args.output_dir,args.min_free_gib*GIB,attempt,args.merge_budget_gib*GIB)
                    all_inputs = [r for value in accepted for r in value["inputs"]]
                    if [r["name"] for r in all_inputs]!=[n for b in plan["batches"] for n in b["archives"]]:
                        raise RuntimeError("Global source coverage differs from plan")
                    coverage = {"start":plan["start"],"end":plan["end"],"interval":"[start,end)",
                                "source_archives":[r["name"] for r in all_inputs],"requested_hours":len(all_inputs),
                                "verified_hours":len(all_inputs),"missing_source_hours":[],
                                "event_dates_use_utc_event_time":True,"archive_presence_does_not_prove_capture_completeness":True}
                    with timed(attempt / "timing_merge.json","final_merge",is_parent=True), monitor_space(
                            args.raw_dir,args.output_dir,attempt,args.min_free_gib*GIB,args.merge_budget_gib*GIB):
                        guard()
                        summary = merge_outputs([f for a in accepted for f in a["fragments"]],attempt / "result",
                                                all_inputs,coverage,args.sqlite_cache_mib,guard)
                    final = {"identity":identity,"attempt":str(attempt.relative_to(args.output_dir)),
                             "summary":summary,"retained_files":inventory(attempt)}
                    write_json(final_marker,final)
                run.update(state="completed",final_output=str((args.output_dir / final["attempt"] / "result").resolve()),finished_at=utc_now())
                write_json(run_path,run)
        except BaseException as error:
            run.update(state="error",error=f"{type(error).__name__}: {error}",finished_at=utc_now())
            write_json(run_path,run)
            raise
    return run


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start",required=True)
    p.add_argument("--end",required=True)
    p.add_argument("--batch-hours",type=int,default=24)
    p.add_argument("--raw-dir",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--spark-config",default="L4",help="L1/L4/D4 or JSON config path")
    p.add_argument("--spark-master",help="Override master endpoint, required for D4 template")
    p.add_argument("--spark-submit",default="spark-submit")
    p.add_argument("--spark-conf",action="append",default=[],help="Repeatable spark.key=value override; saved in run identity")
    p.add_argument("--cleanup",choices=["retain","accepted-raw"],default="retain")
    p.add_argument("--engine",choices=["spark","python"],default="spark",help="python builds a real reference; it is not Spark verification")
    p.add_argument("--base-url",default="https://data.gharchive.org")
    p.add_argument("--min-free-gib",type=float,default=2)
    p.add_argument("--batch-budget-gib",type=float,default=16)
    p.add_argument("--merge-budget-gib",type=float,default=24)
    p.add_argument("--sqlite-cache-mib",type=int,default=128)
    p.add_argument("--plan-only",action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if any(not (0 < v < float("inf")) for v in (args.batch_budget_gib,args.merge_budget_gib,args.sqlite_cache_mib)) or not (0 <= args.min_free_gib < float("inf")):
            raise ValueError("Budgets must be finite, positive (min-free may be zero)")
        plan = make_plan(args.start,args.end,args.batch_hours)
        spark = load_spark(args.spark_config,args.spark_master,args.spark_conf)
        if args.plan_only:
            print(json.dumps({"plan":plan,"spark":spark,"engine":args.engine,"cleanup":args.cleanup,
                              "raw_dir":str(args.raw_dir),"output_dir":str(args.output_dir)},indent=2))
        else:
            run = execute(args,plan,spark)
            print(json.dumps({"state":run["state"],"final_output":run["final_output"]}))
    except (Exception,KeyboardInterrupt) as error:
        print(f"Pipeline failed: {type(error).__name__}: {error}",file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
