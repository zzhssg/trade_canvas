from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class FactorScaffoldCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tmpdir.name)
        self.script_path = Path(__file__).resolve().parents[1] / "scripts" / "new_factor_scaffold.py"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.script_path), *args],
            cwd=str(self.repo_root),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_cli_generates_processor_and_bundle_files(self) -> None:
        proc = self._run(
            "--repo-root",
            str(self.repo_root),
            "--factor",
            "trend_break",
            "--depends-on",
            "pivot,pen",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

        processor_file = self.repo_root / "backend/app/factor/processor_trend_break.py"
        bundle_file = self.repo_root / "backend/app/factor/bundles/trend_break.py"
        self.assertTrue(processor_file.exists())
        self.assertTrue(bundle_file.exists())

        processor_text = processor_file.read_text(encoding="utf-8")
        bundle_text = bundle_file.read_text(encoding="utf-8")
        self.assertIn("class TrendBreakProcessor", processor_text)
        self.assertIn('factor_name="trend_break"', processor_text)
        self.assertIn('depends_on=("pivot", "pen",)', processor_text)
        self.assertIn("class TrendBreakSlicePlugin", bundle_text)
        self.assertIn('event_kind="trend_break.event"', bundle_text)

    def test_cli_rejects_invalid_factor_name(self) -> None:
        proc = self._run(
            "--repo-root",
            str(self.repo_root),
            "--factor",
            "Trend-Break",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("factor_name_invalid:Trend-Break", proc.stderr)

    def test_cli_dry_run_does_not_write_files(self) -> None:
        proc = self._run(
            "--repo-root",
            str(self.repo_root),
            "--factor",
            "trend_break",
            "--dry-run",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[dry-run] factor scaffold ready: trend_break", proc.stdout)

        processor_file = self.repo_root / "backend/app/factor/processor_trend_break.py"
        bundle_file = self.repo_root / "backend/app/factor/bundles/trend_break.py"
        self.assertFalse(processor_file.exists())
        self.assertFalse(bundle_file.exists())


if __name__ == "__main__":
    unittest.main()
