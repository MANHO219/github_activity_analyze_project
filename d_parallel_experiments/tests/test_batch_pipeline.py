"""Real synthetic archives exercise global decisions and lifecycle; no VM/JVM."""
import contextlib
import copy
from datetime import datetime, timedelta, timezone
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT / "d_parallel_experiments/scripts"))
import run_batch_pipeline as runner
import verify_results
import summarize_results
from gharchive_a.common import sha256_file, write_json
from rolling_pipeline import batch_support as support
from rolling_pipeline.batch_merge import merge_outputs
import pyarrow.dataset as ds


def event(identifier,payload="p",repo=1,name="owner/repo"):
    return {"id":str(identifier),"type":"PushEvent","created_at":"2024-01-30T00:01:00Z",
            "repo":{"id":repo,"name":name},"actor":{"id":2,"login":"actor"},"payload":{"x":payload}}


def fixture(root):
    root.mkdir()
    records = {0:[event(1),event(1),event(2),event(3)],1:[event(2,"q")],7:[event(1)],12:[event(1)],
               14:[event(2)],23:[event(5,repo=2,name="所有者/旧名")],
               24:[event(6,repo=2,name="所有者/新名")],25:[event(1)],26:[event(2)],27:[event(3,"q")],47:[event(7)]}
    optional = event(4,repo=3)
    optional.pop("actor")
    optional["repo"].pop("name")
    records[6] = [optional]
    start = datetime(2024,1,31,tzinfo=timezone.utc)
    for i in range(48):
        hour = start+timedelta(hours=i)
        with gzip.open(root / f"{hour:%Y-%m-%d}-{hour.hour}.json.gz","wb") as handle:
            for row in records.get(i,[]):
                handle.write(json.dumps(row,ensure_ascii=False).encode()+b"\n")
            if i==0:
                handle.write(b"bad{\n\n")


class PlanningTests(unittest.TestCase):
    def test_two_days_and_tail_and_month(self):
        for window,count in ((6,8),(12,4),(24,2)):
            p = support.make_plan("2024-01-15","2024-01-17",window)
            self.assertEqual(len(p["batches"]),count)
            names = [n for b in p["batches"] for n in b["archives"]]
            self.assertEqual(len(names),48)
            self.assertEqual(len(set(names)),48)
        p = support.make_plan("2024-01-31T20:00Z","2024-02-01T05:00Z",6)
        self.assertEqual([len(b["archives"]) for b in p["batches"]],[6,3])
        self.assertEqual(len(support.make_plan("2024-01-01","2024-02-01",24)["batches"]),31)

    def test_leap_year_timezone_and_rejections(self):
        self.assertEqual(len(support.make_plan("2024-02-28","2024-03-01",24)["batches"]),2)
        self.assertEqual(support.make_plan("2025-01-01T08:00+08:00","2025-01-01T10:00+08:00",6)["start"],"2025-01-01T00:00:00Z")
        self.assertEqual(len(support.make_plan("2024-12-31T23:00Z","2025-01-01T02:00Z",2)["batches"]),2)
        for start,end,window in (("2024-01-01","2024-01-01",6),("2024-01-02","2024-01-01",6),
                                 ("2024-01-01T00:30Z","2024-01-02",6),("2024-01-01T00:00","2024-01-02",6),
                                 ("2024-01-01","2024-01-02",0)):
            with self.assertRaises(ValueError):
                support.make_plan(start,end,window)

    def test_plan_only_does_not_write_or_download(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            result = subprocess.run([sys.executable,str(Path(runner.__file__)),"--start","2024-01-31T20:00Z",
                                     "--end","2024-02-01T05:00Z","--batch-hours","6","--raw-dir",str(base / "raw"),
                                     "--output-dir",str(base / "out"),"--plan-only"],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(list(base.iterdir()),[])
            self.assertEqual(len(json.loads(result.stdout)["plan"]["batches"]),2)

    def test_shared_submit_logic_and_d4_explicit_endpoint(self):
        with self.assertRaises(ValueError):
            runner.load_spark("D4")
        for mode,master in (("L1","local[1]"),("L4","local[4]"),("D4","spark://example:7077")):
            cfg = runner.load_spark(mode,master)
            args = runner.parser().parse_args(["--start","2024-01-01","--end","2024-01-02","--raw-dir","raw","--output-dir","out"])
            command = runner.spark_command(args,cfg,Path("cfg.json"),Path("out"))
            self.assertIn(master,command)
            self.assertIn("spark.sql.shuffle.partitions=12",command)
            self.assertTrue(any("spark_batch_job.py" in part for part in command))
        with self.assertRaises(ValueError):
            runner.load_spark("L4",overrides=["spark.sql.session.timeZone=Europe/London"])


class RollingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        fixture(self.raw)

    def tearDown(self):
        self.temp.cleanup()

    def args(self,window=24,output="run",**kwargs):
        args = runner.parser().parse_args(["--start","2024-01-31","--end","2024-02-02","--batch-hours",str(window),
            "--raw-dir",str(self.raw),"--output-dir",str(self.root / output),"--engine","python","--min-free-gib","0"])
        for k,v in kwargs.items():
            setattr(args,k,v)
        return args

    def execute(self,args):
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.execute(args,support.make_plan(args.start,args.end,args.batch_hours),runner.load_spark(args.spark_config))

    def test_window_invariance_and_known_conflict_outcomes(self):
        outputs = []
        for window in (6,12,24):
            args = self.args(window,"run"+str(window))
            run = self.execute(args)
            folder = Path(run["final_output"])
            rows = ds.dataset(folder / "events_clean.parquet",format="parquet").to_table().to_pylist()
            self.assertEqual([r["event_id"] for r in rows],["1","4","5","6","7"])
            self.assertEqual(rows[0]["source_line"],1)
            self.assertTrue(all(r["event_date"].isoformat()=="2024-01-30" for r in rows))
            self.assertTrue(all(r["time_outside_file_hour"] for r in rows))
            self.assertIsNone(rows[1]["actor_id"])
            stats = support.read_json(folder / "summary.json")["counts"]
            self.assertEqual(stats,{"valid_occurrences":15,"final_events":5,"duplicate_occurrences_removed":4,
                                    "conflicting_event_ids":2,"conflicting_occurrences_excluded":6})
            outputs.append(args.output_dir)
        for i,right in enumerate(outputs[1:]):
            self.assertTrue(verify_results.compare_runs(outputs[0],right,self.root / f"cmp{i}")["passed"])
        report = summarize_results.summarize(outputs[0])
        self.assertEqual(report["input_files"],48)
        self.assertEqual(report["summary"]["final_events"],5)

    def test_resume_skips_only_reverified_outputs_and_rejects_identity_changes(self):
        args = self.args()
        run = self.execute(args)
        with patch.object(runner,"clean",side_effect=AssertionError("must skip")),patch.object(runner,"download",side_effect=AssertionError("must skip")):
            self.assertEqual(self.execute(args)["state"],"completed")
        changed = copy.copy(args)
        changed.batch_hours = 6
        with self.assertRaisesRegex(RuntimeError,"Incompatible"):
            self.execute(changed)
        marker = next((args.output_dir / "batches").glob("*/accepted.json"))
        accepted = support.read_json(marker)
        bad = args.output_dir / accepted["attempt"] / accepted["retained_files"][0]["path"]
        bad.write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError,"changed"):
            self.execute(args)

    def test_failure_retained_retry_uses_cache_and_new_attempt(self):
        args = self.args()
        original = runner.clean
        def fail(*a,**kw):
            a[2].mkdir()
            (a[2] / "failure.txt").write_text("evidence")
            raise RuntimeError("injected cleaning failure")
        with patch.object(runner,"clean",side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,"injected"):
                self.execute(args)
        self.assertEqual(support.read_json(args.output_dir / "run.json")["state"],"error")
        with patch("urllib.request.urlopen",side_effect=AssertionError("inputs should be cached")):
            self.assertEqual(self.execute(args)["state"],"completed")
        self.assertTrue(list(args.output_dir.rglob("failure.txt")))
        self.assertTrue(list(args.output_dir.glob("batches/*/attempt-0002")))
        self.assertTrue(any(r["state"]=="error" for r in summarize_results.summarize(args.output_dir)["timing_records"]))

    def test_final_merge_interruption_resumes_without_recomputing_batches(self):
        args = self.args()
        with patch.object(runner,"merge_outputs",side_effect=RuntimeError("merge interrupted")):
            with self.assertRaisesRegex(RuntimeError,"merge interrupted"):
                self.execute(args)
        with patch.object(runner,"clean",side_effect=AssertionError("skip accepted")):
            self.assertEqual(self.execute(args)["state"],"completed")
        self.assertTrue((args.output_dir / "merge/attempt-0001/timing_merge.json").exists())
        self.assertTrue((args.output_dir / "merge/attempt-0002/result/summary.json").exists())

    def test_empty_and_missing_archives_are_distinct(self):
        args = self.args(start="2024-01-31T02:00Z",end="2024-01-31T03:00Z")
        run = self.execute(args)
        self.assertEqual(ds.dataset(Path(run["final_output"]) / "events_clean.parquet",format="parquet").count_rows(),0)
        args = self.args(output="missing",start="2024-01-31T02:00Z",end="2024-01-31T03:00Z")
        (self.raw / "2024-01-31-2.json.gz").unlink()
        with patch("urllib.request.urlopen",side_effect=OSError("missing fixture")):
            with self.assertRaises(RuntimeError):
                self.execute(args)

    def test_acceptance_interruption_retries_and_changed_input_is_refused(self):
        args = self.args(start="2024-01-31",end="2024-01-31T01:00Z")
        with patch.object(runner,"validate_fragment",side_effect=RuntimeError("accept interrupted")):
            with self.assertRaisesRegex(RuntimeError,"accept interrupted"):
                self.execute(args)
        with gzip.open(self.raw / "2024-01-31-0.json.gz","ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(RuntimeError,"input changed"):
            self.execute(args)

    def test_budget_guard_and_output_lock(self):
        args = self.args(batch_budget_gib=1e-9)
        with self.assertRaisesRegex(RuntimeError,"budget"):
            self.execute(args)
        with support.exclusive_lock(self.root / "lock"):
            with self.assertRaisesRegex(RuntimeError,"Another pipeline"):
                with support.exclusive_lock(self.root / "lock"):
                    pass

    def test_comparator_rejects_equal_but_internally_wrong_candidates(self):
        args = self.args(start="2024-01-31",end="2024-01-31T01:00Z")
        run = self.execute(args)
        final = Path(run["final_output"])
        candidate = final / "repo_candidates.csv"
        text = candidate.read_text(encoding="utf-8")
        candidate.write_text(text.replace("owner/repo","incorrect/name"),encoding="utf-8")
        # Simulate a separately accepted but logically incorrect producer:
        # checksum agreement alone must not establish correctness.
        marker = args.output_dir / "final_accepted.json"
        value = support.read_json(marker)
        value["retained_files"] = support.inventory(args.output_dir / value["attempt"])
        write_json(marker,value)
        result = verify_results.compare_runs(args.output_dir,args.output_dir,self.root / "bad-comparison")
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["left_candidates_match_events"])

    def test_spark_submission_bridge_and_effective_configuration_guard(self):
        args = self.args(output="spark-bridge",start="2024-01-31",end="2024-01-31T01:00Z",engine="spark")
        spark = runner.load_spark("L4")
        def fixture_job(command,log,guard):
            cfg = support.read_json(Path(command[command.index("--config")+1]))
            out = Path(command[command.index("--output")+1])
            # This stands in for persisted Spark files, not a real Spark run.
            runner.clean(cfg,args.raw_dir,out)
            runner.python_valid_index(out)
            write_json(out / "effective_spark_config.json",dict(spark["conf"],**{"spark.master":"local[4]","spark.driver.memory":"4g"}))
        with patch.object(runner,"run_spark",side_effect=fixture_job):
            self.assertEqual(self.execute(args)["state"],"completed")
        args.output_dir = self.root / "wrong-spark-config"
        def wrong_config(command,log,guard):
            fixture_job(command,log,guard)
            out = Path(command[command.index("--output")+1])
            write_json(out / "effective_spark_config.json",{"spark.master":"local[1]"})
        with patch.object(runner,"run_spark",side_effect=wrong_config):
            with self.assertRaisesRegex(RuntimeError,"effective config"):
                self.execute(args)

    def test_exact_comparison_keeps_duplicate_multiplicity(self):
        from rolling_pipeline.batch_merge import create_db,exact_difference
        db = create_db(self.root / "multiplicity.sqlite3")
        try:
            db.executescript("CREATE TABLE a (id TEXT); CREATE TABLE b (id TEXT); INSERT INTO a VALUES ('1'),('1'); INSERT INTO b VALUES ('1');")
            self.assertEqual(exact_difference(db,"a","b",["id"]),[1,1])
        finally:
            db.close()


class CleanupTests(unittest.TestCase):
    def test_unaccepted_changed_hash_traversal_and_partial_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            folder = root / "batch"
            folder.mkdir()
            write_json(raw / ".batch-owner.json",{"run_id":"run"})
            rows = []
            for h in (0,1):
                p = raw / f"2024-01-15-{h}.json.gz"
                p.write_bytes(b"registered")
                rows.append({"name":p.name,"bytes":p.stat().st_size,"sha256":sha256_file(p),"owner_run":"run"})
            keep = raw / "unregistered.json.gz"
            keep.write_bytes(b"keep")
            accepted = {"state":"processed","inputs":rows}
            with self.assertRaisesRegex(RuntimeError,"accepted"):
                support.cleanup_raw(raw,folder,accepted,"run")
            accepted["state"] = "accepted"
            original_write = support.write_json
            failed = [False]
            def interrupted(path,value):
                if Path(path).name=="cleanup.json" and "deleted" in value.get("files",{}).values() and not failed[0]:
                    failed[0] = True
                    raise RuntimeError("after unlink")
                return original_write(path,value)
            with patch.object(support,"write_json",side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError,"after unlink"):
                    support.cleanup_raw(raw,folder,accepted,"run")
            self.assertTrue(support.cleanup_raw(raw,folder,accepted,"run")["completed"])
            self.assertTrue(keep.exists())
            self.assertFalse((raw / rows[0]["name"]).exists())
            for name in ("../2024-01-15-0.json.gz","..\\2024-01-15-0.json.gz"):
                with self.assertRaises(ValueError):
                    support.safe_raw(raw,name)

    def test_real_download_ownership_clean_resume_and_preserve_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            raw,out = base / "raw",base / "out"
            args = runner.parser().parse_args(["--start","2024-01-15","--end","2024-01-15T02:00Z", "--raw-dir",str(raw),
                "--output-dir",str(out),"--engine","python","--cleanup","accepted-raw","--min-free-gib","0"])
            payload = gzip.compress((json.dumps(event(1))+"\n").encode())
            class Response(io.BytesIO):
                status=200
                headers={"Content-Length":str(len(payload))}
            with patch("urllib.request.urlopen",side_effect=lambda *a,**k:Response(payload)),contextlib.redirect_stdout(io.StringIO()):
                runner.execute(args,support.make_plan(args.start,args.end,24),runner.load_spark("L4"))
            self.assertFalse(list(raw.glob("*.json.gz")))
            with patch.object(runner,"download",side_effect=AssertionError("must not redownload")),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.execute(args,support.make_plan(args.start,args.end,24),runner.load_spark("L4"))["state"],"completed")
            self.assertTrue(support.read_json(next(out.glob("batches/*/cleanup.json")))["completed"])
            cached = base / "cached"
            cached.mkdir()
            (cached / "keep").write_text("historical")
            args.raw_dir,args.output_dir = cached,base / "other"
            with self.assertRaisesRegex(RuntimeError,"NEW empty"):
                runner.execute(args,support.make_plan(args.start,args.end,24),runner.load_spark("L4"))

    def test_hash_change_symlink_and_foreign_owner_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            folder = root / "batch"
            folder.mkdir()
            write_json(raw / ".batch-owner.json",{"run_id":"run"})
            p = raw / "2024-01-15-0.json.gz"
            p.write_bytes(b"first")
            row = {"name":p.name,"bytes":5,"sha256":sha256_file(p),"owner_run":"run"}
            p.write_bytes(b"other")
            with self.assertRaisesRegex(RuntimeError,"changed"):
                support.cleanup_raw(raw,folder,{"state":"accepted","inputs":[row]},"run")
            self.assertTrue(p.exists())
            foreign = dict(row,owner_run=None)
            self.assertTrue(support.cleanup_raw(raw,root / "foreign",{"state":"accepted","inputs":[foreign]},"run")["completed"])
            self.assertTrue(p.exists())
            # Windows may not grant symlink creation; test containment through a
            # mocked symlink flag as well, so refusal is still exercised there.
            with patch.object(Path,"is_symlink",return_value=True):
                with self.assertRaises(ValueError):
                    support.safe_raw(raw,p.name)


class DiskSamplingTests(unittest.TestCase):
    def test_directory_removed_between_discovery_and_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "retained.bin").write_bytes(b"retained")
            transient = root / "_temporary"
            transient.mkdir()
            original_scandir = support.os.scandir
            removed = []
            def racing_scandir(path):
                if Path(path) == transient and transient.exists():
                    transient.rmdir()
                    removed.append(True)
                return original_scandir(path)
            with patch.object(support.os,"scandir",side_effect=racing_scandir):
                self.assertEqual(support.tree_bytes(root),len(b"retained"))
            self.assertTrue(removed)

    def test_permission_failure_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(support.os,"scandir",side_effect=PermissionError("denied")):
                with self.assertRaises(PermissionError):
                    support.tree_bytes(Path(temp))


class TimingSummaryTests(unittest.TestCase):
    def test_cleanup_failure_and_retry_are_reported_without_changing_records(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            failed = root / "invocations/attempt-0001/batch_cleanup.json"
            retry = root / "invocations/attempt-0002/batch_cleanup.json"
            with self.assertRaisesRegex(RuntimeError,"interruption"):
                with support.timed(failed,"raw_cleanup"):
                    raise RuntimeError("interruption")
            with support.timed(retry,"raw_cleanup"):
                pass
            with support.timed(root / "invocations/attempt-0002/timing.json","invocation",is_parent=True):
                pass
            write_json(root / "batches/batch/cleanup.json",{"completed":True,"files":{"owned.json.gz":"deleted"}})
            before = {p: p.read_bytes() for p in root.rglob("*.json")}
            rows = summarize_results.collect_timings(root)
            cleanup = [r for r in rows if r["stage"]=="raw_cleanup"]
            self.assertEqual([r["state"] for r in cleanup],["error","completed"])
            self.assertEqual([r["exit_code"] for r in cleanup],[1,0])
            self.assertTrue(all(r["elapsed_seconds"]>0 for r in cleanup))
            self.assertEqual(len(rows),3)
            self.assertEqual(sum(bool(r.get("is_parent")) for r in rows),1)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob("*.json")})


class LockProtocolTests(unittest.TestCase):
    def test_reentry_does_not_release_outer_process_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "lock"
            probe = ("import sys; from pathlib import Path; "
                     f"sys.path.insert(0,{str(PROJECT / 'a_data_pipeline')!r}); "
                     "from rolling_pipeline.batch_support import exclusive_lock\n"
                     "try:\n with exclusive_lock(Path(sys.argv[1])): pass\n"
                     "except RuntimeError: raise SystemExit(2)\n")
            with support.exclusive_lock(lock):
                with self.assertRaisesRegex(RuntimeError,"Another pipeline"):
                    with support.exclusive_lock(lock):
                        pass
                child = subprocess.run([sys.executable,"-c",probe,str(lock)],capture_output=True,text=True)
                self.assertEqual(child.returncode,2,child.stderr)
            child = subprocess.run([sys.executable,"-c",probe,str(lock)],capture_output=True,text=True)
            self.assertEqual(child.returncode,0,child.stderr)


class WorkerEvidenceTests(unittest.TestCase):
    def test_requires_two_distinct_worker_hosts(self):
        with patch.object(summarize_results,"read_run",side_effect=AssertionError("reject invalid hosts before reading a run")):
            for hosts in (["worker-one","worker-one"], ["worker-one"], ["worker-one",""]):
                with self.subTest(hosts=hosts):
                    with self.assertRaisesRegex(ValueError,"two distinct"):
                        summarize_results.worker_evidence(Path("unused"),Path("unused"),hosts)

    def test_requires_success_on_both_workers_and_application_end(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            logs = root / "logs"
            logs.mkdir()
            fragment = root / "fragment"
            fragment.mkdir()
            write_json(fragment / "application.json",{"application_id":"app-test"})
            write_json(root / "batches/batch/accepted.json",{"fragments":[{"valid":str(fragment / "valid.parquet")} ]})
            run = {"identity":{"spark":{"master":"spark://test:7077"},"plan":{"batches":[{"id":"batch"}]}}}
            events = [{"Event":"SparkListenerApplicationStart","App ID":"app-test"}]
            for host in ("worker-one","worker-two"):
                events.append({"Event":"SparkListenerTaskEnd","Task End Reason":{"Reason":"Success"},"Task Info":{"Host":host}})
            events.append({"Event":"SparkListenerApplicationEnd"})
            path = logs / "app-test"
            path.write_text("\n".join(json.dumps(e) for e in events),encoding="utf-8")
            with patch.object(summarize_results,"read_run",return_value=(run,None,None,None)):
                self.assertTrue(summarize_results.worker_evidence(root,logs,["worker-one","worker-two"])["passed"])
                with self.assertRaises(RuntimeError):
                    summarize_results.worker_evidence(root,logs,["worker-one","absent-worker"])
                path.write_text("\n".join(json.dumps(e) for e in events[:-1]),encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    summarize_results.worker_evidence(root,logs,["worker-one","worker-two"])


if __name__=="__main__":
    unittest.main()
