"""Build the offline HTML explanation from a completed A sample run.

Only documentation files are written. Original archives and run artifacts are
opened for reading; SQLite connections in data_guide_model use mode=ro.
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "docs"))
from data_guide_model import build_snapshot


def esc(value):
    return html.escape(str(value), quote=True)


def pretty(value):
    return esc(json.dumps(value, ensure_ascii=False, indent=2))


def byte_size(number):
    for suffix, divisor in (("GiB",2**30),("MiB",2**20),("KiB",2**10)):
        if number >= divisor:
            return f"{number/divisor:.1f} {suffix}"
    return f"{number} B"


def table(headers, rows, class_=""):
    head = "".join(f"<th scope='col'>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<div class='table-scroll {class_}'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def source_button(reference, label=None):
    return f"<button class='source-link' type='button' data-source='{esc(reference)}'>{esc(label or reference)}</button>"


def location_tree(snapshot, stage, names):
    """Render a compact, fully rooted tree at the point where data is explained."""
    prefix = "data/raw" if stage == "raw" else f"{snapshot['run_path']}/{stage}"
    items = {Path(item["path"]).name: item for item in snapshot["artifacts"] if item["path"].rsplit("/", 1)[0] == prefix}
    leaves = []
    for name in names:
        item = items.get(name)
        if item is None:
            continue
        suffix = "/" if item["is_directory"] else ""
        kind = "目录，内部是表的分片" if item["is_directory"] else "文件"
        leaves.append(f"<li><button type='button' class='locate-file' data-locate='{esc(item['path'])}'><code>{esc(name + suffix)}</code></button><span class='tree-note'>{kind} · {esc(item['grain'])}</span></li>")
    branch = "<ul class='mini-tree'>" + "".join(leaves) + "</ul>"
    for directory in reversed(prefix.split("/")):
        branch = f"<ul class='mini-tree'><li><code class='folder-label'>{esc(directory)}/</code>{branch}</li></ul>"
    return f"<div class='location-box'><p class='location-label'>实际存放位置 · 点击文件可定位到完整说明</p><code class='folder-label'>a_data_pipeline/</code>{branch}</div>"


def aggregate_figure(snapshot):
    repo = snapshot["repo_example"]
    daily = snapshot["daily_example"]
    bars = []
    total = repo["event_count"]
    event_lines = "".join(f"<code>{esc(row['event_time'].split('T')[-1].removesuffix('Z'))} · {esc(row['event_type'])}</code>" for row in snapshot["event_preview"][:3])
    for row in daily:
        count = row["event_count"]
        bars.append(f"<div class='count-bar-row'><code>{esc(row['event_type'])}</code><div class='count-bar-track'><span style='width:{100 * count / total:.4f}%'></span></div><strong>{count}</strong></div>")
    return f"""<figure class='explain-figure' aria-labelledby='aggregate-caption'>
      <figcaption id='aggregate-caption'><span class='figure-number'>图 2</span><strong>同一批事件，按不同问题整理成不同的表</strong></figcaption>
      <p class='muted'>取真实仓库 <code>{esc(repo['repo_name'])}</code> 的本小时事件来放大观察。</p>
      <div class='aggregate-layout'>
       <div class='event-stack'><span class='badge output'>事件明细</span><strong class='big-count'>{total}<small>行</small></strong><p>一行 = 一次活动</p><div class='event-paper'><code>repo_id = {repo['repo_id']}</code>{event_lines}<span>… 共 {total} 条</span></div><p class='muted'>在事件表中筛选这一个仓库；完整事件表还有其他仓库。</p></div>
       <div class='aggregate-results'>
        <div class='aggregate-result'><div class='aggregate-action'><span aria-hidden='true'>→</span><code>按 repo_id 汇总</code></div><div class='result-card'><div><span class='badge output'>仓库候选清单</span><strong>1 行</strong></div><p>这个仓库只占一行，<code>event_count = {total}</code>，还保存首见、末见和名称。</p></div></div>
        <div class='aggregate-result'><div class='aggregate-action'><span aria-hidden='true'>→</span><code>按仓库 × 日期 × 类型计数</code></div><div class='result-card'><div><span class='badge output'>活动计数表</span><strong>{len(daily)} 行</strong></div><div class='count-bars'>{''.join(bars)}</div><p class='count-check'>各行计数相加 = <strong>{total}</strong> 次事件；日期相同，类型不同。</p></div></div>
       </div>
      </div>
      <p class='figure-footnote'>这里展示三种视角：事件明细保留每次活动，仓库清单汇总每个仓库，计数表汇总每类活动。当前范围仍是一个小时。</p>
    </figure>"""


def cleaning_graph(snapshot):
    """File-level provenance graph for the Python path, using the completed run's counts."""
    prefix = snapshot["run_path"] + "/python/"
    quality = snapshot["quality"]
    artifacts = {item["path"]: item for item in snapshot["artifacts"]}
    raw_path = next(item["path"] for item in snapshot["artifacts"] if item["category"] == "raw")
    def box(x, y, title, lines, category, filename=None, href="#stage-python", width=210):
        path = raw_path if category == "raw" else prefix + filename if filename else None
        action = f" data-locate='{esc(path)}'" if path else ""
        tooltip = "a_data_pipeline/" + path if path else "scripts/clean_sample.py → gharchive_a/clean.py"
        texts = "".join(f"<text class='subtext' x='{x+15}' y='{y+53+i*20}'>{esc(line)}</text>" for i,line in enumerate(lines))
        return f"<a href='{href}'{action} class='graph-link'><title>{esc(tooltip)}</title><rect class='node {category}-node' x='{x}' y='{y}' width='{width}' height='105' rx='8'/><text x='{x+15}' y='{y+28}'>{esc(title)}</text>{texts}</a>"
    rejected = artifacts[prefix+"rejected_records.jsonl"]["rows"]
    flagged = artifacts[prefix+"flagged_records.jsonl"]["rows"]
    nodes = [
        box(10,20,"原始 JSON 行",["data/raw/",f"{quality['nonempty_lines']:,} 个非空行"],"raw",href="#files"),
        box(275,20,"解析与字段校验",["records.normalize_line()","UTF-8 → JSON → 共同字段"],"process"),
        box(540,20,"有效记录",["working.sqlite3 / valid_events",f"去重前 {quality['line_status_counts'].get('valid',0):,} 行"],"data","working.sqlite3"),
        box(10,210,"标记后保留",["flagged_records.jsonl",f"本次 {flagged:,} 行；有效事件仍保留"],"report","flagged_records.jsonl"),
        box(275,210,"解析 / 关键字段失败",["rejected_records.jsonl",f"排除 {rejected:,} 行"],"audit","rejected_records.jsonl"),
        box(540,250,"按事件 ID 和内容哈希",["clean.py / clean()","判定重复或内容冲突"],"process"),
        box(10,420,"相同内容的重复出现",["duplicate_records.jsonl",f"移除 {quality['duplicates_removed']:,} 行"],"audit","duplicate_records.jsonl"),
        box(275,420,"相同 ID 的不同内容",["conflicting_records.jsonl",f"暂排除 {quality['conflict_occurrences_excluded']:,} 行"],"audit","conflicting_records.jsonl"),
        box(540,510,"清洗事件",["working.sqlite3 / cleaned_events",f"最终保留 {quality['cleaned_events']:,} 行"],"data","working.sqlite3"),
        box(790,330,"导出事件明细",["events_clean.parquet/",f"{quality['cleaned_events']:,} 行；每行一次事件"],"data","events_clean.parquet",width=230),
        box(790,510,"按仓库汇总",["repo_candidates.csv",f"{quality['clean_unique_repos']:,} 行；每行一个仓库"],"data","repo_candidates.csv",width=230),
        box(790,690,"按仓库 / 日期 / 类型",["repo_daily_counts.csv",f"{artifacts[prefix+'repo_daily_counts.csv']['rows']:,} 行计数"],"data","repo_daily_counts.csv",width=230),
    ]
    edges = [
        ("M220 72 H275",247,58,"读取"),("M485 72 H540",511,58,"保留"),
        ("M330 125 V163 H115 V210",170,152,"写标记；有效事件仍走主线"),
        ("M380 125 V210",390,179,"排除"),("M645 125 V250",659,195,"去重 / 冲突分组"),
        ("M540 333 H515 V360 H115 V420",125,350,"同内容：记录多余出现"),
        ("M540 345 H505 V385 H380 V420",294,405,"多种内容：记录全部出现"),
        ("M645 355 V510",659,466,"保留无冲突 ID 的首次出现"),
        ("M750 562 H767 V382 H790",767,362,"导出"),
        ("M750 562 H790",771,548,"汇总"),
        ("M750 562 H767 V742 H790",776,674,"计数"),
    ]
    paths = "".join(f"<path class='edge' marker-end='url(#clean-arrow)' d='{path}'/><text class='edge-label' x='{x}' y='{y}'>{esc(label)}</text>" for path,x,y,label in edges)
    return f"""<figure class='graph-figure explain-figure' aria-labelledby='clean-graph-caption'>
      <figcaption id='clean-graph-caption'><span class='figure-number'>关系图 B</span><strong>Python 清洗时，记录怎样分流到不同文件</strong></figcaption>
      <p class='muted'>沿箭头读。实线是读取、写出或汇总关系；有问题的记录写到旁支，保留的记录继续沿主线处理。</p>
      <div class='graph-toolbar' role='group' aria-label='调整清洗分流图大小'><button type='button' data-graph-action='minus'>− 缩小</button><button type='button' data-graph-action='fit'>全图</button><button type='button' data-graph-action='plus'>＋ 放大</button><span class='muted'>放大后可左右滑动；点击文件节点查看完整路径</span></div>
      <div class='graph-scroll'><svg class='lineage-diagram graph-visual cleaning-graph' viewBox='0 0 1035 815' role='group' aria-label='原始行经过解析校验形成有效记录；标记、排除、重复和冲突分别另存；清洗事件导出为明细、仓库清单和活动计数。'>
      <defs><marker id='clean-arrow' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' markerHeight='7' orient='auto'><path d='M 0 0 L 10 5 L 0 10 z' fill='var(--muted)'/></marker></defs>{paths}{''.join(nodes)}</svg></div>
      <p class='figure-footnote'>所有 Python 结果位于 <code>{esc(prefix)}</code>。图中的 SQLite 节点表示同一数据库里的不同内部表；重复和冲突文件保存排除过程。问题标记本身不会使有效记录被排除。各节点数字来自当前样本的实际记录。</p>
    </figure>"""


def stage_html(stage, snapshot):
    actual = snapshot["run_summary"]["stages"].get(stage["id"], {})
    badge = "本次已完成" if actual.get("completed") else "本次未运行"
    refs = "".join(source_button(ref) for ref in stage["code"])
    relevant = {"download":["download_manifest.json"], "inspection":["raw_examples.json", "inspection_summary.json"],
                "python":["working.sqlite3", "events_clean.parquet", "repo_candidates.csv", "repo_daily_counts.csv"],
                "spark":["valid_before_dedup.parquet", "events_clean.parquet", "repo_daily_counts.csv"],
                "comparison":["comparison_summary.json", "parquet_validation.json"]}
    return f"""<article class='stage' id='stage-{stage['id']}'>
    <div class='stage-title'><span class='step-number'>{stage['number']}</span><div><p class='eyebrow'>{esc(stage['script'])}</p><h3>{esc(stage['title'])}</h3></div><span class='badge output'>{badge}</span></div>
    <div class='stage-grid'><div><h4>输入是什么</h4><p>{esc(stage['input'])}</p></div><div><h4>脚本具体做什么</h4><p>{esc(stage['change'])}</p></div><div><h4>产生了什么</h4><p>{esc(stage['output'])}</p></div><div><h4>谁会继续使用</h4><p>{esc(stage['used_by'])}</p></div></div>
    <p class='source-row'><strong>命令入口</strong> <a href='scripts/{esc(stage['script'])}'><code>scripts/{esc(stage['script'])}</code></a> <span>→ 实际逻辑</span> {source_button(stage['function'])}</p>
    <details class='stage-location'><summary>这一阶段的结果存在哪里？展开目录树</summary>{location_tree(snapshot,stage['id'],relevant[stage['id']])}</details>
    <details><summary>查看这一阶段关联的函数</summary><div class='source-buttons'>{refs}</div></details>
    </article>"""


def build_html(snapshot, template):
    quality = snapshot["quality"]
    first = snapshot["examples"][0]
    raw = first["raw"]
    repo = snapshot["repo_example"]
    run_prefix = snapshot["run_path"]
    n = lambda key: f"{quality[key]:,}"
    fields = "".join(f"<button type='button' class='field-button' data-field='{esc(f['name'])}' aria-pressed='{'true' if i == 0 else 'false'}'><code>{esc(f['name'])}</code><span>{esc(f['kind'])}</span></button>" for i,f in enumerate(snapshot["schema"]))
    schema_rows = [[f"<code>{esc(f['name'])}</code>", f"<code>{esc(f['origin'])}</code>", esc(f['kind']), f"<code>{esc(f['type'])}</code>", esc(f['detail'])] for f in snapshot["schema"]]
    event_rows = [[f"<code>{esc(r['event_id'])}</code>", esc(r['event_time']), esc(r['repo_name']), f"<code>{esc(r['event_type'])}</code>", esc(r['actor_login'])] for r in snapshot["event_preview"]]
    daily_rows = [[str(r['repo_id']), esc(r['event_date']), f"<code>{esc(r['event_type'])}</code>", f"<strong>{r['event_count']:,}</strong>"] for r in snapshot["daily_example"]]
    repo_rows = [[str(repo['repo_id']), esc(repo['repo_name']), esc(repo['first_observed_at']), esc(repo['last_observed_at']), f"{repo['event_count']:,}", str(repo['observed_name_count'])]]
    sql_purposes = {"valid_events":"每条通过字段校验的记录（去重前），加 sequence 与完整内容哈希。", "event_groups":"每个 event_id 的出现数、内容版本数、首次序号。", "cleaned_events":"无冲突 ID 的首次出现；作为导出和统计的基础。", "daily_counts":"清洗事件按仓库、日期、类型分组计数。", "duplicate_occurrences":"指向相同内容的其他出现；这是视图，不是又一批独立样本。", "conflicting_occurrences":"指向冲突 ID 的所有有效出现；等待复核。"}
    sql_rows = [[f"<code>{esc(t['name'])}</code>", esc(t['kind']), f"{t['rows']:,}", esc(sql_purposes.get(t['name'], "数据库内部结构"))] for t in snapshot["sql_tables"]]
    raw_fields = [("id","标识本次事件","提取并规范为 event_id"),("type","事件类型","提取为 event_type"),("actor","发起者对象，含 id/login/头像等","提取 ID 与 login；其他详情留在原档案"),("repo","仓库对象，含 id/name/url","提取 ID 与名称；url 留在原档案"),("payload","事件详情；Push、PR、Watch 的结构不同","本轮不展开成共同表列；完整详情留在原档案"),("public","该事件的可见性标志","保留在原档案；当前规则没有按此字段追加过滤"),("created_at","事件发生时间，ISO 8601","规范为 UTC event_time，并派生 event_date"),("org","组织对象（此记录提供）","保留在原档案")]
    raw_rows = [[f"<code>{esc(key)}</code>", esc(mean), esc(use)] for key,mean,use in raw_fields]
    type_rows = [[f"<code>{esc(kind)}</code>", f"{number:,}"] for kind,number in sorted(snapshot["inspection"]["event_types"].items(), key=lambda kv:(-kv[1],kv[0]))]
    compare_rows = [[f"<code>{esc(key)}</code>", "通过" if value else "未通过"] for key,value in (snapshot["comparison"] or {}).get("checks",{}).items()]
    env = snapshot["run_status"]["environment"]
    statuses = quality["line_status_counts"]
    parse_errors = statuses.get("parse_error", 0)
    invalid = statuses.get("invalid", 0)
    scope_count = len(snapshot["input_manifest"]["observed_files"])
    created_run_day = datetime.fromisoformat(snapshot["run_status"]["started_at"]).astimezone(ZoneInfo("Asia/Hong_Kong")).date().isoformat()
    problem_note = ("本次各类问题为 0，所以行数没有减少。结构规范、来源追溯和质量核对仍已执行。"
                    if parse_errors + invalid + quality["duplicates_removed"] + quality["conflict_occurrences_excluded"] + quality["time_outside_file_hour_before_dedup"] + sum(quality["optional_issues_before_dedup"].values()) == 0
                    else "本次存在排除或去重记录，具体数量和来源在质量摘要及各类问题文件中保留。")
    replacements = {
        "@@SNAPSHOT@@":json.dumps(snapshot, ensure_ascii=True, separators=(",",":"), allow_nan=False).replace("<", "\\u003c"),
        "@@DATE@@":esc(snapshot["document_date"]), "@@RUN@@":esc(snapshot["run_name"]), "@@RUN_PATH@@":esc(run_prefix),
        "@@RAW_NAME@@":esc(snapshot["input_manifest"]["observed_files"][0]["name"]),
        "@@RAW_SIZE@@":byte_size(sum(f["bytes"] for f in snapshot["input_manifest"]["observed_files"])),
        "@@EVENT_N@@":n("cleaned_events"), "@@REPO_N@@":n("clean_unique_repos"),
        "@@GROUP_N@@":f"{next(t['rows'] for t in snapshot['sql_tables'] if t['name']=='daily_counts'):,}",
        "@@SCOPE_TEXT@@":f"{scope_count} 个小时档案", "@@RUN_DAY@@":created_run_day,
        "@@PARSE_ERROR_N@@":f"{parse_errors:,}", "@@PARSE_SUCCESS_N@@":f"{quality['nonempty_lines']-parse_errors:,}",
        "@@INVALID_N@@":f"{invalid:,}",
        "@@VALID_N@@":f"{statuses.get('valid',0):,}", "@@DUP_N@@":f"{quality['duplicates_removed']:,}",
        "@@CONFLICT_N@@":f"{quality['conflict_occurrences_excluded']:,}", "@@QUALITY_NOTE@@":esc(problem_note),
        "@@ACTUAL_TIME_MIN@@":esc(snapshot['inspection']['event_time_min']), "@@ACTUAL_TIME_MAX@@":esc(snapshot['inspection']['event_time_max']),
        "@@RAW_N@@":f"{quality['nonempty_lines']:,}", "@@TYPE_N@@":str(len(snapshot['inspection']['event_types'])),
        "@@ARTIFACT_N@@":str(len(snapshot['artifacts'])),
        "@@RAW_PREVIEW@@":pretty(raw), "@@CLEAN_PREVIEW@@":pretty(first["clean"]),
        "@@RAW_LOCATION@@":location_tree(snapshot,"raw",[f["name"] for f in snapshot["input_manifest"]["observed_files"]]),
        "@@B_INPUT_LOCATION@@":location_tree(snapshot,"python",["repo_candidates.csv","repo_name_history.csv","events_preview.csv"]),
        "@@EVENT_LOCATION@@":location_tree(snapshot,"python",["events_clean.parquet","events_clean.csv.gz","events_preview.csv"]),
        "@@REPO_LOCATION@@":location_tree(snapshot,"python",["repo_candidates.csv","repo_name_history.csv"]),
        "@@DAILY_LOCATION@@":location_tree(snapshot,"python",["repo_daily_counts.csv","repo_daily_counts.parquet"]),
        "@@AGGREGATE_FIGURE@@":aggregate_figure(snapshot),
        "@@CLEANING_GRAPH@@":cleaning_graph(snapshot),
        "@@RAW_FIELDS@@":table(["原始字段","含义","本轮怎样使用"],raw_rows),
        "@@TYPES@@":table(["事件类型（清洗前有效记录）","出现条数"],type_rows),
        "@@FIELD_BUTTONS@@":fields,"@@SCHEMA@@":table(["处理后列名","来自哪里 / 怎么产生","变化类型","Parquet 类型","用途与处理规则"],schema_rows),
        "@@STAGES@@":"".join(stage_html(stage,snapshot) for stage in snapshot["stages"]),
        "@@EVENT_TABLE@@":table(["事件 ID","事件时间 UTC","仓库名","事件类型","actor"],event_rows),
        "@@REPO_TABLE@@":table(["repo_id","repo_name","first_observed_at","last_observed_at","event_count","observed_name_count"],repo_rows),
        "@@DAILY_TABLE@@":table(["repo_id","event_date","event_type","event_count"],daily_rows),
        "@@REPO_NAME@@":esc(repo["repo_name"]),"@@REPO_TOTAL@@":f"{repo['event_count']:,}","@@REPO_GROUP_N@@":str(len(snapshot['daily_example'])),
        "@@SQL_TABLES@@":table(["内部表 / 视图","结构","实际行数","保存了什么"],sql_rows),
        "@@COMPARE@@":table(["自动检查项","本次结果"],compare_rows),
        "@@CONFIG@@":pretty(snapshot["config"]),
        "@@DOWNLOAD_REPORT@@":pretty(snapshot["download_manifest"]),
        "@@ACQUISITION_REPORT@@":pretty(snapshot["initial_acquisition"]) if snapshot["initial_acquisition"] else "此项目目录未找到另存的首次下载报告。",
        "@@PYTHON_VERSION@@":esc(env["python"].split()[0]),"@@PYARROW_VERSION@@":esc(env['packages']['pyarrow']),"@@SPARK_VERSION@@":esc(env['packages']['pyspark']),
        "@@MATCH_CODE@@":"一致" if snapshot['code_matches_run'] else "已变化，页面代码快照与原运行记录不同",
        "@@SHA@@":esc(snapshot["input_manifest"]["observed_files"][0]["sha256"]),
    }
    html_text = template
    for marker,value in replacements.items():
        html_text = html_text.replace(marker,value)
    if "@@" in html_text:
        raise ValueError("Unexpanded template marker")
    return html_text


def main():
    parser = argparse.ArgumentParser(description="Create a self-contained group explanation of the A data pipeline")
    parser.add_argument("--run-dir", type=Path, default=ROOT/"runs/20240115_1hour_handoff")
    parser.add_argument("--output", type=Path, default=ROOT/"数据处理全解.html")
    parser.add_argument("--document-date", default=datetime.now(ZoneInfo("Asia/Hong_Kong")).date().isoformat(), help="Document date in the user's timezone")
    args = parser.parse_args()
    snapshot = build_snapshot(args.run_dir,args.document_date)
    text = build_html(snapshot,(ROOT/"docs/data-guide.template.html").read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(text,encoding="utf-8")
    snapshot_file = ROOT/"docs/data-guide-snapshot.json"
    snapshot_file.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"html":str(args.output.resolve()),"snapshot":str(snapshot_file),"artifacts":len(snapshot['artifacts']),
                      "fields":len(snapshot['schema']),"example_events":len(snapshot['examples']),"code_matches_run":snapshot['code_matches_run']},ensure_ascii=False))


if __name__ == "__main__":
    main()
