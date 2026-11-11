"""Retrying a failed download preserves registered partial files."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from weekly_pipeline import preserve_partial_files


class ResumeTest(unittest.TestCase):
    def test_partial_is_preserved_and_retry_name_is_available(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            day = root / "2024-01-19"
            manifest_dir = day / "attempt-01/download"
            manifest_dir.mkdir(parents=True)
            raw = root / "raw/2024-01-19"
            raw.mkdir(parents=True)
            partial = raw / "2024-01-19-0.json.gz.download.attempt-1.part"
            partial.write_bytes(b"partial bytes")
            (manifest_dir / "download_manifest.json").write_text(json.dumps({"files": [
                {"attempts": [{"partial_file": str(partial)}]}]}), encoding="utf-8")
            preserve_partial_files(day, raw)
            record = json.loads((day / "preserved_partials.json").read_text())[0]
            self.assertFalse(partial.exists())
            self.assertEqual(Path(record["preserved"]).read_bytes(), b"partial bytes")
            partial.write_bytes(b"new retry")
            self.assertEqual(partial.read_bytes(), b"new retry")


if __name__ == "__main__":
    unittest.main()
