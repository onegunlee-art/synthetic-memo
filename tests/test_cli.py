from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MemoCliAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cwd = Path(self.temp_dir.name)
        self.data_path = self.cwd / "items.json"

    def run_memo(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "synthetic_memo", *arguments],
            cwd=self.cwd,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )

    def test_scenario_add_list_and_restart(self) -> None:
        first = self.run_memo("add", "검수 요청 보내기")
        second = self.run_memo("add", "백업 확인")
        listed = self.run_memo("list")
        restarted = self.run_memo("list")

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("[1]", first.stdout)
        self.assertIn("[2]", second.stdout)
        for result in (listed, restarted):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[ ] 1  검수 요청 보내기", result.stdout)
            self.assertIn("[ ] 2  백업 확인", result.stdout)

        payload = json.loads(self.data_path.read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in payload["items"]], [1, 2])

    def test_scenario_done_preserves_other_item_and_restart_state(self) -> None:
        self.run_memo("add", "검수 요청 보내기")
        self.run_memo("add", "백업 확인")

        completed = self.run_memo("done", "1")
        listed = self.run_memo("list")
        restarted = self.run_memo("list")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("완료", completed.stdout)
        for result in (listed, restarted):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[x] 1  검수 요청 보내기", result.stdout)
            self.assertIn("[ ] 2  백업 확인", result.stdout)

    def test_empty_text_is_exit_2_and_does_not_create_store(self) -> None:
        result = self.run_memo("add", "   ")

        self.assertEqual(result.returncode, 2)
        self.assertIn("비어", result.stderr)
        self.assertFalse(self.data_path.exists())

    def test_unknown_and_non_numeric_ids_are_exit_2_without_modification(self) -> None:
        self.run_memo("add", "원본")
        before = self.data_path.read_bytes()

        unknown = self.run_memo("done", "999")
        non_numeric = self.run_memo("done", "abc")

        self.assertEqual(unknown.returncode, 2)
        self.assertIn("찾을 수 없습니다", unknown.stderr)
        self.assertEqual(non_numeric.returncode, 2)
        self.assertIn("사용법", non_numeric.stderr)
        self.assertEqual(self.data_path.read_bytes(), before)

    def test_corrupt_store_reports_easy_error_without_traceback_or_overwrite(self) -> None:
        original = b"not-json"
        self.data_path.write_bytes(original)

        result = self.run_memo("list")

        self.assertEqual(result.returncode, 2)
        self.assertIn("손상", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.data_path.read_bytes(), original)

    def test_help_documents_local_commands_and_storage(self) -> None:
        result = self.run_memo("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("add", result.stdout)
        self.assertIn("list", result.stdout)
        self.assertIn("done", result.stdout)
        self.assertIn("items.json", result.stdout)
        self.assertIn("$env:PYTHONPATH='src'", result.stdout)


if __name__ == "__main__":
    unittest.main()
