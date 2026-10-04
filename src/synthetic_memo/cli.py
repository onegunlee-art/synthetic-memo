"""Command-line interface for the local synthetic memo product."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .storage import (
    CorruptStoreError,
    InvalidMemoError,
    ItemNotFoundError,
    MemoStore,
)


def _configure_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memo",
        description=(
            "인터넷 없이 현재 폴더의 items.json에 메모를 저장합니다.\n"
            "PowerShell 실행:\n"
            "  $env:PYTHONPATH='src'; python -m synthetic_memo <명령>"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", metavar="명령")

    add_parser = commands.add_parser("add", help="메모 추가")
    add_parser.add_argument("text", help="저장할 메모 내용")

    commands.add_parser("list", help="전체 메모 보기")

    done_parser = commands.add_parser("done", help="ID로 완료 처리")
    done_parser.add_argument("item_id", help="완료할 숫자 ID")
    return parser


def _parse_item_id(raw: str) -> int:
    try:
        item_id = int(raw)
    except ValueError as exc:
        raise InvalidMemoError(
            "ID는 숫자여야 합니다. 사용법: memo done <id>"
        ) from exc
    if item_id < 1:
        raise InvalidMemoError("ID는 1 이상이어야 합니다. 사용법: memo done <id>")
    return item_id


def main(argv: Sequence[str] | None = None, *, data_path: str | Path = "items.json") -> int:
    _configure_utf8_streams()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command is None:
        parser.print_help(sys.stderr)
        return 2

    store = MemoStore(data_path)
    try:
        if arguments.command == "add":
            item = store.add(arguments.text)
            print(f"추가됨: [{item['id']}] {item['text']}")
            return 0

        if arguments.command == "list":
            items = store.list_items()
            if not items:
                print("저장된 메모가 없습니다.")
                return 0
            for item in items:
                marker = "x" if item["done"] else " "
                print(f"[{marker}] {item['id']}  {item['text']}")
            return 0

        if arguments.command == "done":
            item = store.mark_done(_parse_item_id(arguments.item_id))
            print(f"완료: [{item['id']}] {item['text']}")
            return 0
    except (CorruptStoreError, InvalidMemoError, ItemNotFoundError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2

    parser.error("알 수 없는 명령입니다.")
    return 2
