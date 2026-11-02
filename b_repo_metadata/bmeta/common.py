"""共享路径、CSV/JSON 读写与 UTC 时间工具（B 阶段）。

约定：
- 所有写出的时间戳都是 UTC，格式 ``YYYY-MM-DDTHH:MM:SSZ``；
- CSV 一律 UTF-8（无 BOM），换行符为 ``\\n``，便于 git diff 与跨平台复核；
- 本模块不联网、不读 token，仅做路径与文件操作。
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

B_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = B_ROOT.parent
A_HANDOFF = PROJECT_ROOT / "a_data_pipeline" / "runs" / "20240115_1hour_handoff"
DEFAULT_CANDIDATES = A_HANDOFF / "python" / "repo_candidates.csv"
DEFAULT_NAME_HISTORY = A_HANDOFF / "python" / "repo_name_history.csv"
DEFAULT_EVENTS_PARQUET = A_HANDOFF / "python" / "events_clean.parquet"
DEFAULT_CONFIG = B_ROOT / "config" / "pilot.json"

UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> str:
    """当前 UTC 时间，秒级，带 ``Z`` 后缀。"""
    return datetime.now(timezone.utc).strftime(UTC_FORMAT)


def sha256_file(path: os.PathLike[str] | str, chunk_size: int = 1 << 20) -> str:
    """文件 SHA-256；用于记录输入名单的来源与可复现性。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_dir(path: os.PathLike[str] | str) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def read_json(path: os.PathLike[str] | str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: os.PathLike[str] | str, payload: Any, *, indent: int = 2) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=indent, sort_keys=False)
        handle.write("\n")
    return target


def read_csv(path: os.PathLike[str] | str) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(
    path: os.PathLike[str] | str,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> Path:
    """按固定列顺序写 CSV；缺失列写为空字符串。"""
    target = Path(path)
    ensure_dir(target.parent)
    with open(target, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: "" if row.get(name) is None else row.get(name, "") for name in fieldnames})
    return target


def append_jsonl(path: os.PathLike[str] | str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    ensure_dir(target.parent)
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_jsonl(path: os.PathLike[str] | str) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(target, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_config(path: os.PathLike[str] | str = DEFAULT_CONFIG) -> dict[str, Any]:
    """读取 pilot 配置，并把配置内的相对路径按**配置文件所在目录**解析。

    这样移动运行目录或从其他工作目录调用脚本时，输入路径仍然稳定。
    """
    config_path = Path(path).resolve()
    config = read_json(config_path)
    for key in ("candidates_csv", "name_history_csv", "rules_file"):
        value = config.get(key)
        if value and not Path(value).is_absolute():
            config[key] = str((config_path.parent / value).resolve())
    return config


def project_relative(path: os.PathLike[str] | str) -> str:
    """把绝对路径表示成相对仓库根目录的 POSIX 风格路径，便于写进 JSON。"""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def update_run_summary(path: os.PathLike[str] | str, section: str, payload: Mapping[str, Any]) -> Path:
    """把某个阶段的结果合并进 ``run_summary.json``。

    每个脚本只更新自己的段落（``fetch``/``labels``/``join`` 等），重复运行时
    覆盖同一段，不会产生多份互相矛盾的摘要。
    """
    target = Path(path)
    summary: dict[str, Any] = {}
    if target.exists():
        try:
            summary = read_json(target)
        except (OSError, json.JSONDecodeError):
            summary = {}
    if not isinstance(summary, dict):
        summary = {}
    summary[section] = payload
    summary["updated_at_utc"] = utc_now()
    write_json(target, summary)
    return target


def environment_snapshot() -> dict[str, Any]:
    """记录复跑所需的最小环境信息（不包含任何本机路径以外的敏感内容）。"""
    import platform
    import sys

    try:
        from . import __version__ as package_version
    except Exception:  # pragma: no cover - 仅在包外直接运行时触发
        package_version = "unknown"
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "package_version": package_version,
    }
