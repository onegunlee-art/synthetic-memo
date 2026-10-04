from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_memo.storage import (  # noqa: E402
    CorruptStoreError,
    InvalidMemoError,
    ItemNotFoundError,
    MemoStore,
)


class MemoStoreAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "items.json"

    def test_add_list_done_persists_across_restarts_without_reusing_ids(self) -> None:
        first_store = MemoStore(self.path)
        first = first_store.add("검수 요청 보내기")
        second = first_store.add("백업 확인")

        self.assertEqual((first["id"], second["id"]), (1, 2))
        self.assertFalse(first["done"])
        self.assertFalse(second["done"])

        restarted = MemoStore(self.path)
        self.assertEqual(restarted.list_items(), [first, second])
        completed = restarted.mark_done(1)
        self.assertTrue(completed["done"])

        after_second_restart = MemoStore(self.path)
        items = after_second_restart.list_items()
        self.assertEqual([item["id"] for item in items], [1, 2])
        self.assertEqual([item["done"] for item in items], [True, False])
        third = after_second_restart.add("후속 작업")
        self.assertEqual(third["id"], 3)

    def test_utf8_korean_round_trip_and_valid_json(self) -> None:
        text = "한글 메모 ☕ — 검수 완료"
        MemoStore(self.path).add(text)

        decoded = self.path.read_text(encoding="utf-8")
        payload = json.loads(decoded)
        self.assertEqual(payload["items"][0]["text"], text)
        self.assertNotIn("\\u", decoded)

    def test_missing_item_does_not_modify_original_file(self) -> None:
        store = MemoStore(self.path)
        store.add("원본")
        before = self.path.read_bytes()

        with self.assertRaises(ItemNotFoundError):
            store.mark_done(999)

        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_or_whitespace_only_memo_is_rejected_without_creating_file(self) -> None:
        store = MemoStore(self.path)

        for value in ("", "   ", "\t\n"):
            with self.subTest(value=value):
                with self.assertRaises(InvalidMemoError):
                    store.add(value)

        self.assertFalse(self.path.exists())

    def test_corrupt_json_is_never_overwritten(self) -> None:
        original = b'{"version": 1, "items": ['
        self.path.write_bytes(original)

        with self.assertRaises(CorruptStoreError):
            MemoStore(self.path).add("덮어쓰면 안 됨")

        self.assertEqual(self.path.read_bytes(), original)

    def test_failed_atomic_replace_leaves_existing_file_unchanged(self) -> None:
        store = MemoStore(self.path)
        store.add("원본")
        before = self.path.read_bytes()

        with mock.patch("synthetic_memo.storage.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                store.add("새 항목")

        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
