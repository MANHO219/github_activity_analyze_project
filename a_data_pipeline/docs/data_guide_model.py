"""Read-only evidence collection for the standalone group data guide.

This module only reads an existing completed run. It does not download archives,
clean records, change the SQLite databases, or run Spark.
"""
from __future__ import annotations

import ast
import csv
import gzip
import hashlib
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENT_FIELDS = ["event_id", "event_type", "event_time", "repo_id", "repo_name", "actor_id", "actor_login", "event_date", "source_file", "source_line", "source_hour", "time_outside_file_hour", "optional_field_issues"]

FIELD_GUIDE = [
    ("event_id", "id", "规范化", "标识一次事件；作为去重键。合法正整数 ID 转为字符串。"),
    ("event_type", "type", "提取", "区分推送、PR、Issue 等活动。非空字符串；未知事件类型也保留。"),
    ("event_time", "created_at", "规范化", "事件发生时刻；解析带时区的时间并转成 UTC。它不是仓库创建时间。"),
    ("repo_id", "repo.id", "规范化", "标识仓库，作为仓库表和事件表的连接键。合法正整数，保存为 int64。"),
    ("repo_name", "repo.name", "提取", "样本中观察到的 owner/repo 名称；缺失或无效时置空并保留事件。"),
    ("actor_id", "actor.id", "规范化", "发起者 ID；缺失或无效时置空并标记。后续统计参与者时可使用。"),
    ("actor_login", "actor.login", "提取", "发起者账号名，可能是用户或机器人；本轮保留机器人活动。"),
    ("event_date", "从 event_time 取 UTC 日期", "推导", "方便按日期分组。按日期分组不意味着已经读取完整一天。"),
    ("source_file", "读取时记录输入文件名", "追溯", "说明这一事件来自哪个小时档案。用于回查原始记录。"),
    ("source_line", "解压后逐行计数，从 1 开始", "追溯", "原始档案中的行号，包含前面的空行；与事件 ID 是不同概念。"),
    ("source_hour", "从文件名解析日期和小时", "追溯", "记录档案标注的 UTC 小时；例如文件名最后的 -0 表示 00 时。"),
    ("time_outside_file_hour", "比较 event_time 所在小时与 source_hour", "标记", "二者不一致时为 true；标记后仍保留事件，供检查档案时间偏差。"),
    ("optional_field_issues", "检查 repo_name / actor_id / actor_login", "标记", "保存可选字段问题列表；[] 表示未发现这几项问题。CSV/SQLite 中是 JSON 文本，Parquet 中是真正的字符串列表。"),
]

STAGES = [
    {"id":"download","number":"01","title":"获取原始档案并验证可读性","script":"download_sample.py","function":"gharchive_a/download.py:download",
     "input":"日期、小时、GH Archive 下载地址，以及可能已存在的原始缓存文件。",
     "change":"按日期/小时生成文件名；下载到 .part，完整解压检查后计算 SHA-256，再生成正式 .json.gz。已有文件校验后复用。这里保持原始事件内容。",
     "output":"data/raw/*.json.gz 是原始输入；download_manifest.json 是脚本产生的获取记录。失败的 .part 另留存。",
     "used_by":"原始档案会分别被 inspection、Python 清洗和 Spark 清洗读取。下载报告用于核实来源、缓存状态和失败小时。",
     "code":["gharchive_a/download.py:download","gharchive_a/download.py:verify_archive"]},
    {"id":"inspection","number":"02","title":"查看原始内容并形成检查报告","script":"inspect_sample.py","function":"gharchive_a/inspect.py:inspect",
     "input":"原始 .json.gz 档案；不是 download_manifest.json 中的事件数据。",
     "change":"逐行读原始字节，解码 UTF-8，解析 JSON，使用统一规则检查共同字段；统计清洗前的事件分布、仓库数和异常，保留前 5 条记录及其解析结果。",
     "output":"raw_examples.json、inspection_summary.json、file_statistics.csv、raw_event_types.csv、raw_anomalies.jsonl。它们都是处理产生的预览/报告。",
     "used_by":"给人检查数据结构和覆盖。Python 与 Spark 会重新读取原始档案；不会拿前 5 条预览作为完整数据输入。",
     "code":["gharchive_a/inspect.py:inspect","gharchive_a/records.py:iter_records","gharchive_a/records.py:normalize_line"]},
    {"id":"python","number":"03","title":"Python 清洗、去重、汇总与导出","script":"clean_sample.py","function":"gharchive_a/clean.py:clean",
     "input":"同一份原始 .json.gz；共同规则来自 records.py。",
     "change":"规范字段后把有效事件存进 working.sqlite3；按事件 ID 和完整内容哈希分组；去除相同内容重复，暂排除冲突 ID；再从清洗事件导出事件表、仓库清单和日期/类型计数。",
     "output":"三张主要分析表、名称历史、清洗前 SQLite、异常/重复/冲突文件、逐小时质量与总质量报告。",
     "used_by":"B 用仓库清单开始补元数据；C 用事件明细和计数开发原型；comparison 读取此路径的 CSV、Parquet 和输入清单来核对。",
     "code":["gharchive_a/clean.py:clean","gharchive_a/records.py:normalize_line","gharchive_a/export.py:export_events","gharchive_a/export.py:export_daily"]},
    {"id":"spark","number":"04","title":"Spark 从原始档案独立计算同样的结果","script":"clean_sample_spark.py","function":"gharchive_a/spark_clean.py:clean_spark",
     "input":"同一份原始 .json.gz；不是 Python 导出的事件表。",
     "change":"把小时文件分配给 Spark 分区；分区内使用相同逐行解析规则，再以明确 schema 建立 DataFrame。去重、冲突处理、分组由 Spark 实现；会话时区和 Parquet 时间格式固定。",
     "output":"对应的事件表、仓库清单、活动计数、问题记录；另外导出 valid_before_dedup.parquet，并记录 Spark 环境和 worker 代码快照。",
     "used_by":"先验证 Spark 算对了；D 后续可在固定输入与任务上设计并行度实验。两套输出是同样本的复算结果，分析选一套使用。",
     "code":["gharchive_a/spark_clean.py:clean_spark","gharchive_a/spark_clean.py:parse_archive","gharchive_a/spark_clean.py:parsed_schema"]},
    {"id":"comparison","number":"05","title":"核对两条计算路径及事件 Parquet 导出","script":"compare_outputs.py","function":"gharchive_a/compare.py:compare",
     "input":"python/ 和 spark/ 的输入清单、quality_summary、events_clean.csv.gz、repo_daily_counts.csv，以及事件 Parquet。",
     "change":"先验证输入文件哈希、请求范围和规则版本相同。导入 comparison.sqlite3，比较事件 ID、全部事件字段及日分组；从事件明细重算日计数；读回事件 Parquet 核对值、行数、UTC 类型与 CSV 一致。",
     "output":"comparison_summary.json、parquet_validation.json、6 类差异样例 CSV、comparison.sqlite3。它们是验证产物。",
     "used_by":"通过核对后交接。当前自动比较范围包括事件表和 CSV 日计数；仓库清单/名称历史、日计数 Parquet 未在此脚本中逐字段自动比较。",
     "code":["gharchive_a/compare.py:compare","gharchive_a/compare.py:check_parquet"]},
]

# Logical artifacts, not internal part files. Actual bytes/rows are collected below.
CATALOG = {
 "HANDOFF.md":("report","run_sample.py","交接入口","本次结果、覆盖范围和优先读取文件的说明。"),
 "resolved_config.json":("config","run_sample.py","实际参数","覆盖命令行后的日期、小时及运行配置；不是事件。"),
 "run_summary.json":("report","run_sample.py","阶段进度","哪几个阶段完成、清洗事件数和覆盖范围。"),
 "stage_status.json":("report","run_sample.py / common.stage_directory","运行状态","开始/结束、成功/失败、版本、参数、环境、源码哈希和耗时。"),
 "pipeline.log":("report","run_sample.py","运行日志","阶段执行及错误追踪；不包含完整事件数据。"),
 "download_manifest.json":("report","download_sample.py","获取记录","文件来源 URL、字节数、SHA-256、缓存或下载、尝试和失败状态。"),
 "input_manifest.json":("report","对应阶段 + common.select_inputs","输入清单","实际读取的档案、哈希、请求/缺失小时及覆盖边界。"),
 "raw_examples.json":("preview","inspect_sample.py","前 5 个非空记录","带 raw_line 原文副本和规范字段、status 的检查预览。不是 GH Archive 的原始文件。"),
 "inspection_summary.json":("report","inspect_sample.py","清洗前统计","去重前有效记录的分布、字段问题、仓库数和时间范围。"),
 "file_statistics.csv":("report","inspect_sample.py","一行一个输入档案","清洗前逐档案的行数、解析/字段问题和时间偏离。"),
 "raw_event_types.csv":("report","inspect_sample.py","一行一种事件类型","有效记录在去重前的事件类型计数。"),
 "raw_anomalies.jsonl":("audit","inspect_sample.py","一行一条检查异常","解析失败或关键字段无效的原始行和检查结果。"),
 "working.sqlite3":("intermediate","clean_sample.py","SQLite 表/视图集合","保留清洗前有效记录、去重分组、清洗事件、日计数及重复/冲突视图。"),
 "events_clean.parquet":("output","clean_sample.py / clean_sample_spark.py","一行一次事件","完整清洗事件表；typed Parquet，含 UTC 时间和追溯字段。"),
 "events_clean.csv.gz":("output","clean_sample.py / clean_sample_spark.py","一行一次事件","与事件 Parquet 对应的压缩 CSV；完整数据，不是 100 行预览。"),
 "events_preview.csv":("preview","clean_sample.py / clean_sample_spark.py","前 100 条清洗事件","事件表的查看入口，不能拿它代表完整数据量。"),
 "repo_candidates.csv":("output","clean_sample.py / clean_sample_spark.py","一行一个 repo_id","样本内出现的仓库及首见/末见/事件数；供 B 补标签与元数据。"),
 "repo_name_history.csv":("output","clean_sample.py / clean_sample_spark.py","一行一个 repo_id × 观察名称","保留样本内名称与首见/末见/计数；可回查多名称情况。"),
 "repo_daily_counts.csv":("output","clean_sample.py / clean_sample_spark.py","一行一个 repo_id × UTC 日期 × 类型","计数单位是事件；只有实际出现的组合，没有补完整日或零活动行。"),
 "repo_daily_counts.parquet":("output","clean_sample.py / clean_sample_spark.py","同日计数表","CSV 日计数的 typed Parquet 保存形式。"),
 "rejected_records.jsonl":("audit","clean_sample.py / clean_sample_spark.py","一行一条排除记录","UTF-8/JSON 解析失败或关键字段无效；原始行、原因与来源可回查。"),
 "flagged_records.jsonl":("audit","clean_sample.py / clean_sample_spark.py","一行一条问题标记","可选字段问题或时间偏离；这类事件仍可进入有效记录与后续去重。"),
 "duplicate_records.jsonl":("audit","clean_sample.py / clean_sample_spark.py","一行一个被移除的重复出现","同一 ID、完整内容相同的重复；保留首次来源，记录其他出现。"),
 "conflicting_records.jsonl":("audit","clean_sample.py / clean_sample_spark.py","一行一个冲突 ID 的有效出现","同一 ID 内容不同时，保存所有出现；暂不进入清洗结果。"),
 "hourly_quality.csv":("report","clean_sample.py","一行一个输入档案","逐档案清洗前/后、重复、冲突、时间偏离计数。"),
 "quality_summary.json":("report","对应清洗脚本","质量总报告","行数、类型/仓库数、排除原因、计数核对和覆盖。"),
 "valid_before_dedup.parquet":("intermediate","clean_sample_spark.py","一行一条去重前有效记录","Spark 的审计导出，含共同字段和完整内容哈希；后续计算继续用 DataFrame。"),
 "spark_environment.json":("config","clean_sample_spark.py","Spark 环境记录","master、Java/Python、UTC、时间存储格式及文件读取分区数。"),
 "worker_code.zip":("code","clean_sample_spark.py","包内 Python 源码快照","给 worker 导入共享代码，同时保留本次执行代码；不是事件压缩包。"),
 "comparison_summary.json":("report","compare_outputs.py","核对结论","每项检查是否通过，以及 ID/事件字段/日计数的差异数。"),
 "parquet_validation.json":("report","compare_outputs.py","事件 Parquet 验证","两边事件 Parquet 的字段类型、行数、与 CSV 一致情况。"),
 "comparison.sqlite3":("intermediate","compare_outputs.py","验证用 SQLite","导入左右 CSV、日计数和读回的事件 Parquet，用于集合比较。"),
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_counts(path):
    """Get counts from actual exports, not hard-coded sample numbers."""
    if path.is_dir() and path.suffix == ".parquet":
        import pyarrow.parquet as pq
        return sum(pq.ParquetFile(p).metadata.num_rows for p in path.glob("*.parquet"))
    if path.is_dir() and path.suffix == ".jsonl":
        return sum(sum(1 for line in p.open(encoding="utf-8") if line.strip()) for p in path.glob("*.json"))
    if path.name.endswith(".csv.gz"):
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            return sum(1 for _ in reader)
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            return sum(1 for _ in reader)
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    if path.name == "raw_examples.json":
        return len(read_json(path))
    return None


def size_of(path):
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else path.stat().st_size


def artifact_info(path, run):
    name = path.name
    stage = path.parent.name if path.parent != run else "root"
    if name.endswith("_examples.csv"):
        spec = ("audit", "compare_outputs.py", "最多 100 个差异样例", "从左右集合差中输出 ID、全部事件字段或日计数。0 行表示此比较没有差异。")
    else:
        spec = CATALOG.get(name)
    if spec is None:
        raise ValueError(f"Undocumented logical artifact: {path}")
    if name == "stage_status.json" and stage != "root":
        stage_scripts = {"download":"download_sample.py", "inspection":"inspect_sample.py", "python":"clean_sample.py", "spark":"clean_sample_spark.py", "comparison":"compare_outputs.py"}
        spec = ("report", f"{stage_scripts[stage]} + common.stage_directory", spec[2], spec[3])
    category, producer, grain, purpose = spec
    if stage == "python" and producer == "clean_sample.py / clean_sample_spark.py":
        producer = "scripts/clean_sample.py → clean.py / export.py"
    elif stage == "spark" and producer == "clean_sample.py / clean_sample_spark.py":
        producer = "scripts/clean_sample_spark.py → spark_clean.py（CSV 复用 export.py）"
    if name == "quality_summary.json":
        producer = "scripts/clean_sample.py" if stage == "python" else "scripts/clean_sample_spark.py"
    if name == "input_manifest.json":
        producer = {"inspection":"inspect_sample.py", "python":"clean_sample.py", "spark":"clean_sample_spark.py"}[stage] + " + common.select_inputs"
    relative = Path(os.path.relpath(path, ROOT)).as_posix()
    parts = []
    if path.is_dir():
        parts = [p.name for p in sorted(path.iterdir()) if p.is_file()]
    return {"path": relative, "label": (f"{stage}/" if stage != "root" else "") + name,
            "stage": stage, "category": category, "producer": producer,
            "grain": grain, "purpose": purpose, "bytes": size_of(path), "rows": row_counts(path),
            "is_directory": path.is_dir(), "parts": parts}


def source_snapshots():
    sources = {}
    files = list((ROOT / "gharchive_a").glob("*.py"))
    files.extend(ROOT / "scripts" / name for name in ("download_sample.py", "inspect_sample.py", "clean_sample.py", "clean_sample_spark.py", "compare_outputs.py", "run_sample.py", "_bootstrap.py"))
    for path in sorted(files):
        text = path.read_text(encoding="utf-8")
        functions = {node.name: {"start": node.lineno, "end": node.end_lineno}
                     for node in ast.walk(ast.parse(text)) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        sources[path.relative_to(ROOT).as_posix()] = {"text": text, "functions": functions}
    return sources


def navigation_files(sources):
    """Collect the real supporting paths shown alongside data in the directory tree."""
    notes = {
        "README.md": ("report", "项目运行与交接入口"),
        "B_接手指南.md": ("report", "B 的输入、首批范围、元数据与 AI 标签交付约定"),
        "数据说明_给组员.md": ("report", "简短的数据说明入口"),
        "数据处理全解.html": ("report", "正在阅读的可离线分享说明页"),
        "environment.yml": ("config", "新电脑创建 conda 环境的配置"),
        "environment.lock.osx-arm64.yml": ("config", "Apple Silicon 运行环境的版本记录"),
        "config/sample.json": ("config", "样本日期、小时、文件预算和预览行数"),
        "scripts/build_data_guide.py": ("code", "读取已完成样本，生成本说明页"),
        "docs/data_guide_model.py": ("code", "读取实际样本、源码和文件清单，形成文档证据"),
        "docs/data-guide.template.html": ("code", "本页的版式、图形与交互模板"),
        "docs/data-guide-snapshot.json": ("report", "生成本页时读取的数据与源码快照"),
        "verification/README.md": ("report", "数据管道与说明页的验证记录入口"),
        "verification/RESULTS.md": ("report", "已完成样本的运行与核对结果"),
    }
    entry_notes = {stage["script"]: stage["title"] for stage in STAGES}
    entry_notes.update({"run_sample.py": "按顺序调度整个样本管道", "_bootstrap.py": "使命令入口能导入项目包"})
    for path in sources:
        purpose = entry_notes.get(Path(path).name, "处理逻辑模块；可在本页源码查看器中阅读")
        notes[path] = ("code", purpose)
    return [{"path": path, "category": category, "purpose": purpose,
             "producer": "项目源码 / 文档", "grain": "代码、配置或说明；不包含分析事件行",
             "bytes": (ROOT / path).stat().st_size, "rows": None,
             "is_directory": False, "parts": [], "stage": "support", "support": True}
            for path, (category, purpose) in sorted(notes.items()) if (ROOT / path).is_file()]


def preview(value, path="", cuts=None):
    """A labeled display excerpt; full values remain in the raw archive."""
    cuts = cuts if cuts is not None else []
    if isinstance(value, dict):
        return {key: preview(item, f"{path}.{key}" if path else key, cuts) for key, item in value.items()}
    if isinstance(value, list):
        if len(value) > 1:
            cuts.append({"path": path, "original_items": len(value), "shown_items": 1})
        return [preview(item, f"{path}[0]", cuts) for item in value[:1]]
    if isinstance(value, str) and len(value) > 400:
        cuts.append({"path": path, "original_characters": len(value), "shown_characters": 400})
        return value[:400] + "…"
    return value


def build_snapshot(run, document_date):
    run = Path(run).resolve()
    run_status = read_json(run / "run_summary.json")
    if run_status["state"] != "completed":
        raise ValueError("The data guide requires a completed sample run")
    quality = read_json(run / "python/quality_summary.json")
    inspection = read_json(run / "inspection/inspection_summary.json")
    manifest = read_json(run / "python/input_manifest.json")
    config = read_json(run / "resolved_config.json")
    root_status = read_json(run / "stage_status.json")
    files = {}
    raw_artifacts = []
    for item in manifest["observed_files"]:
        path = Path(item["path"])
        if not path.exists():
            path = ROOT / "data/raw" / item["name"]
        if digest_file(path) != item["sha256"]:
            raise ValueError(f"Raw archive no longer matches this run: {path}")
        files[item["name"]] = path
        raw_artifacts.append({"path": Path(os.path.relpath(path, ROOT)).as_posix(), "label": f"data/raw/{item['name']}",
             "stage":"raw", "category":"raw", "producer":"GH Archive；download_sample.py 获取/验证", "grain":"解压后每个非空行是一个原始 JSON 事件",
             "purpose":"最初输入；保留完整 payload、actor/repo 详情及其他原始字段。", "bytes":path.stat().st_size,
             "rows": quality["nonempty_lines"] if len(files) == 1 and len(manifest["observed_files"]) == 1 else None,
             "is_directory":False, "parts":[], "sha256":item["sha256"]})
    uri = (run / "python/working.sqlite3").as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        first = dict(db.execute("SELECT * FROM cleaned_events ORDER BY sequence LIMIT 1").fetchone())
        repo_id = first["repo_id"]
        case_rows = [first]
        for kind in ("PullRequestEvent", "WatchEvent"):
            row = db.execute("SELECT * FROM cleaned_events WHERE repo_id=? AND event_type=? ORDER BY sequence LIMIT 1", (repo_id, kind)).fetchone()
            if row:
                case_rows.append(dict(row))
        daily = [dict(r) for r in db.execute("SELECT * FROM daily_counts WHERE repo_id=? ORDER BY event_count DESC, event_type", (repo_id,))]
        repo = dict(db.execute("SELECT repo_id, MIN(event_time) AS first_observed_at, MAX(event_time) AS last_observed_at, COUNT(*) AS event_count, COUNT(DISTINCT repo_name) AS observed_name_count FROM cleaned_events WHERE repo_id=?", (repo_id,)).fetchone())
        latest = db.execute("SELECT repo_name FROM cleaned_events WHERE repo_id=? AND repo_name IS NOT NULL ORDER BY event_time DESC,sequence DESC LIMIT 1", (repo_id,)).fetchone()
        repo["repo_name"] = latest[0] if latest else None
        event_rows = [dict(r) for r in db.execute("SELECT * FROM cleaned_events WHERE repo_id=? ORDER BY sequence LIMIT 8", (repo_id,))]
        sql_tables = [{"name":r["name"],"kind":r["type"],"rows":db.execute(f'SELECT COUNT(*) FROM "{r["name"]}"').fetchone()[0]}
                      for r in db.execute("SELECT name,type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name").fetchall()]
    wanted = {(row["source_file"], row["source_line"]): row for row in case_rows}
    raw_records = {}
    for name, path in files.items():
        targets = {line for file_, line in wanted if file_ == name}
        if not targets:
            continue
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if line_no in targets:
                    raw_records[(name, line_no)] = json.loads(line)
                if line_no >= max(targets):
                    break
    examples = []
    for row in case_rows:
        raw = raw_records[(row["source_file"], row["source_line"])]
        core = {key: row[key] for key in EVENT_FIELDS}
        core["optional_field_issues"] = json.loads(core["optional_field_issues"])
        core["time_outside_file_hour"] = bool(core["time_outside_file_hour"])
        cuts = []
        examples.append({"raw":preview(raw, cuts=cuts),"cuts":cuts,"clean":core,
                         "payload_keys":list(raw.get("payload", {})),
                         "commit_count":len(raw.get("payload",{}).get("commits",[]))})
    sources = source_snapshots()
    code_digest = hashlib.sha256()
    for path in sorted((ROOT / "gharchive_a").glob("*.py")):
        code_digest.update(path.name.encode())
        code_digest.update(path.read_bytes())
    artifacts = raw_artifacts
    for parent in [run] + [run / name for name in ("download","inspection","python","spark","comparison") if (run/name).exists()]:
        for path in sorted(parent.iterdir()):
            if path.name.startswith(".") or (parent == run and path.is_dir()):
                continue
            artifacts.append(artifact_info(path, run))
    for stage in STAGES:
        for reference in stage["code"]:
            file_, function = reference.split(":")
            if function not in sources[file_]["functions"]:
                raise ValueError(f"Source reference no longer exists: {reference}")
    schema = []
    types = read_json(run / "comparison/parquet_validation.json")["left"]["types"] if (run / "comparison/parquet_validation.json").exists() else {}
    for key, origin, kind, detail in FIELD_GUIDE:
        schema.append({"name":key,"origin":origin,"kind":kind,"detail":detail,"type":types.get(key, "见字段约定")})
    acquisition_path = ROOT / "runs/real_20240115_download/download_manifest.json"
    acquisition = read_json(acquisition_path) if acquisition_path.exists() else None
    return {"document_date":document_date,"run_name":run.name,"run_path":Path(os.path.relpath(run,ROOT)).as_posix(),
            "config":config,"quality":quality,"inspection":inspection,"input_manifest":manifest,
            "run_status":root_status,"run_summary":run_status,"examples":examples,"event_preview":event_rows,
            "repo_example":repo,"daily_example":daily,"sql_tables":sql_tables,"schema":schema,
            "stages":STAGES,"artifacts":artifacts,"sources":sources,
            "navigation_files":navigation_files(sources),
            "other_runs":[path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "runs").iterdir()) if path.is_dir() and path != run],
            "comparison":read_json(run/"comparison/comparison_summary.json") if (run/"comparison/comparison_summary.json").exists() else None,
            "parquet_validation":read_json(run/"comparison/parquet_validation.json") if (run/"comparison/parquet_validation.json").exists() else None,
            "spark_environment":read_json(run/"spark/spark_environment.json") if (run/"spark/spark_environment.json").exists() else None,
            "download_manifest":read_json(run/"download/download_manifest.json"),
            "initial_acquisition":acquisition,
            "current_code_sha256":code_digest.hexdigest(),"recorded_code_sha256":root_status["environment"]["code_sha256"],
            "code_matches_run":code_digest.hexdigest() == root_status["environment"]["code_sha256"]}
