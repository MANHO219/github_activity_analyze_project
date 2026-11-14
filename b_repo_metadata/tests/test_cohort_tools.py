"""Testing Data: candidate search completeness, review gating and immutable cohorts."""
import csv
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs, urlparse

B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B / "scripts"))
from discover_created_repositories import discover
from freeze_cohort import freeze


class SearchClient:
    base_url = "https://api.github.com"
    calls = 0
    def __init__(self, total=101, incomplete=False):
        self.total, self.incomplete, self.calls = total, incomplete, 0
    def request(self, url):
        self.calls += 1
        page = int(parse_qs(urlparse(url).query)["page"][0])
        items = [{"id": n, "full_name": f"testing/repo{n}", "created_at": "2026-04-01T12:00:00Z"}
                 for n in range((page-1)*100+1, min(page*100, self.total)+1)]
        return SimpleNamespace(http_status=200, body={"total_count": self.total,
                               "incomplete_results": self.incomplete, "items": items})


class CohortToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        from bmeta.common import write_csv
        write_csv(self.root / "metadata.csv", ["repo_id", "api_repo_id", "fetch_status", "repo_created_at"], [
            {"repo_id": 1, "api_repo_id": 1, "fetch_status": "ok_cached", "repo_created_at": "2026-04-01T00:00:00Z"},
            {"repo_id": 2, "api_repo_id": 2, "fetch_status": "ok", "repo_created_at": "2025-04-01T00:00:00Z"},
            {"repo_id": 3, "api_repo_id": 99, "fetch_status": "ok", "repo_created_at": "2026-04-01T00:00:00Z"}])
        write_csv(self.root / "labels.csv", ["repo_id", "ai_label_final", "label_source"],
                  [{"repo_id": n, "ai_label_final": "included", "label_source": "auto_rule"} for n in [1, 2, 3]])

    def freeze(self, **kw):
        return freeze(self.root/"metadata.csv", self.root/"labels.csv", self.root/"frozen", 2026,
                      "2026-04-01", "2026-04-07", **kw)

    def test_review_gate_and_explicit_provisional_snapshot(self):
        with self.assertRaisesRegex(ValueError, "lack manual review"):
            self.freeze()
        self.assertFalse((self.root / "frozen").exists())
        s = self.freeze(allow_auto=True)
        self.assertEqual(s["repo_ids"], [1])
        self.assertEqual(s["status"], "provisional_auto_labels")
        self.assertEqual(s["observation_end_21d"], "2026-04-27")
        with self.assertRaises(FileExistsError):
            self.freeze(allow_auto=True)

    def test_reviewed_labels_freeze_normally(self):
        p = self.root / "labels.csv"
        p.write_text(p.read_text().replace("auto_rule", "manual_review"))
        self.assertEqual(self.freeze()["status"], "reviewed")

    def test_pagination_and_completed_snapshot_protection(self):
        client = SearchClient()
        s = discover(client, "2026-04-01", "2026-04-01", ["topic:ai"], self.root/"search")
        self.assertEqual(s["rows"], 101)
        self.assertEqual(client.calls, 2)
        with self.assertRaises(FileExistsError):
            discover(client, "2026-04-01", "2026-04-01", ["topic:ai"], self.root/"search")

    def test_incomplete_and_over_limit_are_not_finalized(self):
        for i, client in enumerate([SearchClient(1001), SearchClient(1, True)]):
            out = self.root / f"search{i}"
            with self.assertRaises(ValueError):
                discover(client, "2026-04-01", "2026-04-01", ["topic:ai"], out)
            self.assertFalse((out / "pilot_candidates.csv").exists())
