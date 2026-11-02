"""Copy Git-visible project files into a ZIP, without changing the source repository.

Uses an isolated temporary Git directory to apply the project's .gitignore rules.
No source files are staged, committed, deleted, or uploaded.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Build the GitHub sharing copy using .gitignore")
    parser.add_argument("--output", type=Path, default=ROOT.parent / "group_project_github_ready.zip")
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        output.relative_to(ROOT)
    except ValueError:
        pass
    else:
        raise SystemExit("Place the sharing ZIP outside group_project to avoid including it in itself.")
    if output.exists():
        raise SystemExit(f"Output already exists; choose a new --output path: {output}")
    with tempfile.TemporaryDirectory(prefix="cs5488-share-") as temp:
        git_dir = Path(temp) / "index.git"
        subprocess.run(["git", "init", "--bare", "--quiet", str(git_dir)], check=True)
        raw = subprocess.check_output([
            "git", f"--git-dir={git_dir}", f"--work-tree={ROOT}",
            "ls-files", "--others", "--exclude-standard", "-z",
        ], cwd=ROOT)
        names = sorted(path.decode("utf-8") for path in raw.split(b"\0") if path)
    if not names:
        raise SystemExit("No sharing files selected")
    for name in names:
        path = ROOT / name
        if path.is_symlink():
            raise SystemExit(f"Review symlink before sharing: {name}")
        if path.stat().st_size >= 100 * 1024**2:
            raise SystemExit(f"Selected file reaches the regular GitHub file limit: {name}")
    required = "a_data_pipeline/runs/20240115_1hour_handoff/python/repo_candidates.csv"
    if required not in names:
        raise SystemExit("B's candidate input is missing from the sharing selection")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(ROOT / name, "group_project_github_ready/" + name)
    print(json.dumps({
        "archive": str(output), "files": len(names),
        "selected_bytes": sum((ROOT / name).stat().st_size for name in names),
        "zip_bytes": output.stat().st_size,
        "largest_file_bytes": max((ROOT / name).stat().st_size for name in names),
        "b_input_included": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
