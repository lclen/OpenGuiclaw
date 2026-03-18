from __future__ import annotations

import argparse
from pathlib import Path
import sys


def read_text(path: Path, encoding: str) -> str:
    return path.read_text(encoding=encoding)


def write_text(path: Path, content: str, encoding: str) -> None:
    path.write_text(content, encoding=encoding)


def load_value(
    inline_value: str | None,
    file_value: str | None,
    stdin_flag: bool,
    encoding: str,
) -> str | None:
    sources = [inline_value is not None, file_value is not None, stdin_flag]
    if sum(sources) > 1:
        raise ValueError("Only one of inline text, file text, or stdin may be used at a time")
    if inline_value is not None:
        return inline_value
    if file_value is not None:
        return Path(file_value).read_text(encoding=encoding)
    if stdin_flag:
        return sys.stdin.read()
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely edit UTF-8 text files without relying on PowerShell default encoding."
    )
    parser.add_argument("--path", required=True, help="Target file path")
    parser.add_argument("--encoding", default="utf-8", help="Text encoding, default: utf-8")

    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--replace", action="store_true", help="Replace text in file")
    action.add_argument("--append", action="store_true", help="Append text to file")
    action.add_argument("--prepend", action="store_true", help="Prepend text to file")
    action.add_argument("--ensure", action="store_true", help="Append text only if missing")
    action.add_argument("--insert-after", action="store_true", help="Insert text after a marker")
    action.add_argument("--insert-before", action="store_true", help="Insert text before a marker")
    action.add_argument("--show", action="store_true", help="Print file content")

    parser.add_argument("--find", help="Text to find when using --replace")
    parser.add_argument("--find-file", help="Read find text from file when using --replace")
    parser.add_argument("--replace-text", help="Replacement text")
    parser.add_argument("--replace-file", help="Read replacement text from file")

    parser.add_argument("--text", help="Inline text for append/prepend/ensure")
    parser.add_argument("--text-file", help="Read text from file for append/prepend/ensure")
    parser.add_argument("--stdin-text", action="store_true", help="Read text payload from stdin")

    parser.add_argument("--count", type=int, default=-1, help="Replacement count, default: all")
    parser.add_argument("--create", action="store_true", help="Create file and parent dirs if missing")
    parser.add_argument("--check", action="store_true", help="Validate changes and print a short summary")
    parser.add_argument(
        "--marker",
        help="Marker text used with --insert-after or --insert-before",
    )
    parser.add_argument(
        "--marker-file",
        help="Read marker text from file when using --insert-after or --insert-before",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    path = Path(args.path)
    encoding = args.encoding

    if args.show:
        sys.stdout.write(read_text(path, encoding))
        return 0

    if not path.exists():
        if not args.create:
            raise FileNotFoundError(f"File not found: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding=encoding)

    original = read_text(path, encoding)
    updated = original

    if args.replace:
        find_value = load_value(args.find, args.find_file, False, encoding)
        replace_value = load_value(args.replace_text, args.replace_file, False, encoding)
        if find_value is None or replace_value is None:
            raise ValueError("--replace requires both find and replacement text")
        if find_value not in original:
            raise ValueError("Find text not found in target file")
        if args.count == -1:
            updated = original.replace(find_value, replace_value)
        else:
            updated = original.replace(find_value, replace_value, args.count)
    else:
        payload = load_value(args.text, args.text_file, args.stdin_text, encoding)
        if payload is None:
            raise ValueError("This action requires text input")
        if args.append:
            updated = original + payload
        elif args.prepend:
            updated = payload + original
        elif args.ensure:
            updated = original if payload in original else original + payload
        elif args.insert_after or args.insert_before:
            marker_value = load_value(args.marker, args.marker_file, False, encoding)
            if marker_value is None:
                raise ValueError("--insert-after/--insert-before requires marker text")
            marker_index = original.find(marker_value)
            if marker_index == -1:
                raise ValueError("Marker text not found in target file")
            insert_index = marker_index + len(marker_value) if args.insert_after else marker_index
            updated = original[:insert_index] + payload + original[insert_index:]

    if updated != original:
        write_text(path, updated, encoding)

    if args.check:
        verified = read_text(path, encoding)
        status = "unchanged" if verified == original else "updated"
        print(f"{status}: {path}")
        print(f"length={len(verified)} encoding={encoding}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
