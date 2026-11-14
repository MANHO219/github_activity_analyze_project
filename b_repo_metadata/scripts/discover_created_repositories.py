#!/usr/bin/env python3
"""Discover date-qualified candidates; persist API pages and never truncate silently."""
import argparse
from datetime import date, timedelta
from pathlib import Path
import urllib.parse

import _bootstrap  # noqa: F401
from bmeta.api import GitHubRepoClient
from bmeta.common import read_json, write_json, write_csv, sha256_file, utc_now
from bmeta.select import SELECTED_FIELDS


def discover(client, start, end, queries, out):
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    if end < start or not queries:
        raise ValueError("Provide an increasing date range and explicit search queries")
    out = Path(out)
    if (out / "selection.json").exists():
        raise FileExistsError("Completed candidate snapshot exists; use a new output directory")
    spec = {"created_from": str(start), "created_to": str(end), "queries": queries}
    state = out / "search_spec.json"
    if state.exists() and read_json(state) != spec:
        raise ValueError("Resume arguments differ from saved search specification")
    write_json(state, spec)
    repositories, snapshots = {}, []
    current = start
    while current <= end:
        for qi, query in enumerate(queries):
            q = f"{query} created:{current} fork:false is:public"
            page, expected, ids = 1, None, set()
            while True:
                url = client.base_url + "/search/repositories?" + urllib.parse.urlencode(
                    {"q": q, "per_page": 100, "page": page, "sort": "updated", "order": "asc"})
                path = out / "search_pages" / f"{current}_q{qi+1:02d}_p{page:02d}.json"
                if path.exists():
                    saved = read_json(path)
                    if saved["url"] != url:
                        raise ValueError("Cached page URL differs from requested query")
                    body = saved["body"]
                else:
                    response = client.request(url)
                    if response.http_status != 200 or not isinstance(response.body, dict):
                        raise RuntimeError(f"Search failed: HTTP {response.http_status}; rerun to resume")
                    body = response.body
                    write_json(path, {"url": url, "fetched_at": utc_now(), "body": body})
                total = int(body["total_count"])
                if body.get("incomplete_results") or total > 1000:
                    raise ValueError(f"Incomplete or over-1000 search for {q!r}; narrow the query and use a new output directory")
                if expected is not None and total != expected:
                    raise ValueError("Search changed during pagination; repeat in a new directory")
                expected = total
                snapshots.append({"path": str(path), "sha256": sha256_file(path)})
                items = body.get("items", [])
                for item in items:
                    created = date.fromisoformat(item["created_at"][:10])
                    if created != current or item.get("fork") or item.get("private"):
                        raise ValueError("Search returned a repository outside requested creation/public/fork scope")
                    rid = int(item["id"])
                    if rid in ids:
                        raise ValueError("Duplicate within paginated query; repeat in a new directory")
                    ids.add(rid)
                    repositories[rid] = {"repo_id": rid, "repo_name": item["full_name"],
                                         "sample_stratum": "created_date_search", "selection_rank": ""}
                if len(ids) == total:
                    break
                if not items or page >= 10:
                    raise ValueError("Pagination did not retrieve every result; no candidate list finalized")
                page += 1
        current += timedelta(days=1)
    rows = [repositories[k] for k in sorted(repositories)]
    for rank, row in enumerate(rows, 1):
        row["selection_rank"] = rank
    target = out / "pilot_candidates.csv"
    write_csv(target, SELECTED_FIELDS, rows)
    summary = {**spec, "generated_at": utc_now(), "rows": len(rows), "api_calls": client.calls,
               "candidate_sha256": sha256_file(target), "search_pages": snapshots,
               "scope": "Currently public non-fork repositories matching saved queries; not all historical AI repositories"}
    write_json(out / "selection.json", summary)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--created-from", required=True)
    p.add_argument("--created-to", required=True)
    p.add_argument("--query", action="append", required=True, help="Repeat for a union of explicit scopes, e.g. topic:machine-learning")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--interval", type=float, default=2.1)
    a = p.parse_args()
    result = discover(GitHubRepoClient(request_interval_seconds=a.interval),
                      a.created_from, a.created_to, a.query, a.out_dir)
    print(f"Candidate snapshot complete: {result['rows']} repositories")


if __name__ == "__main__":
    main()
