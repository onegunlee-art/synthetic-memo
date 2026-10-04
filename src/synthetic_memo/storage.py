"""Durable, atomic storage for the synthetic memo product."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class MemoStoreError(RuntimeError):
    """Base error for memo storage operations."""


class CorruptStoreError(MemoStoreError):
    """Raised when an existing store is not valid UTF-8 memo JSON."""


class InvalidMemoError(MemoStoreError):
    """Raised when a memo cannot be accepted."""


class ItemNotFoundError(MemoStoreError):
    """Raised when an item ID is absent."""


def _empty_state() -> dict[str, Any]:
    return {"version": 1, "next_id": 1, "items": []}


def _validate_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("version") != 1:
        raise CorruptStoreError("items.json 형식이 올바르지 않습니다.")
    next_id = value.get("next_id")
    items = value.get("items")
    if isinstance(next_id, bool) or not isinstance(next_id, int) or next_id < 1:
        raise CorruptStoreError("items.json의 next_id가 올바르지 않습니다.")
    if not isinstance(items, list):
        raise CorruptStoreError("items.json의 items가 목록이 아닙니다.")

    checked: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "text", "done"}:
            raise CorruptStoreError("items.json에 잘못된 항목이 있습니다.")
        item_id = item["id"]
        text = item["text"]
        done = item["done"]
        if (
            isinstance(item_id, bool)
            or not isinstance(item_id, int)
            or item_id < 1
            or item_id in seen_ids
            or not isinstance(text, str)
            or not text.strip()
            or not isinstance(done, bool)
        ):
            raise CorruptStoreError("items.json에 잘못된 항목이 있습니다.")
        seen_ids.add(item_id)
        checked.append({"id": item_id, "text": text, "done": done})

    if seen_ids and next_id <= max(seen_ids):
        raise CorruptStoreError("items.json의 next_id가 기존 ID보다 크지 않습니다.")
    return {"version": 1, "next_id": next_id, "items": checked}


class MemoStore:
    """Persist memo items in one UTF-8 JSON file with atomic replacement."""

    def __init__(self, path: str | Path = "items.json") -> None:
        self.path = Path(path)

    def list_items(self) -> list[dict[str, Any]]:
        state = self._load()
        return [dict(item) for item in state["items"]]

    def add(self, text: str) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise InvalidMemoError("메모 내용은 비어 있을 수 없습니다.")
        state = self._load()
        item = {"id": state["next_id"], "text": text.strip(), "done": False}
        state["next_id"] += 1
        state["items"].append(item)
        self._write(state)
        return dict(item)

    def mark_done(self, item_id: int) -> dict[str, Any]:
        if isinstance(item_id, bool) or not isinstance(item_id, int) or item_id < 1:
            raise ItemNotFoundError(f"항목 ID {item_id!r}을(를) 찾을 수 없습니다.")
        state = self._load()
        for item in state["items"]:
            if item["id"] == item_id:
                if not item["done"]:
                    item["done"] = True
                    self._write(state)
                return dict(item)
        raise ItemNotFoundError(f"항목 ID {item_id}을(를) 찾을 수 없습니다.")

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return _empty_state()
        try:
            raw = self.path.read_text(encoding="utf-8")
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CorruptStoreError(
                "items.json이 손상되었습니다. 원본을 보존하고 작업을 중단합니다."
            ) from exc
        return _validate_state(value)

    def _write(self, state: dict[str, Any]) -> None:
        checked = _validate_state(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(checked, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
