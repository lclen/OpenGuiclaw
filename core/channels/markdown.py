"""Markdown helpers for IM channel rendering."""

from __future__ import annotations

import re

_MARKDOWN_PATTERNS = [
    r"\*\*[^*]+\*\*",
    r"__[^_]+__",
    r"(?<!\*)\*[^*]+\*(?!\*)",
    r"(?<!_)_[^_]+_(?!_)",
    r"^#{1,6}\s",
    r"\[.+?\]\(.+?\)",
    r"`[^`]+`",
    r"```",
    r"^[-*+]\s",
    r"^\d+\.\s",
    r"^>\s",
]
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")


def contains_markdown(text: str) -> bool:
    if not text:
        return False
    if _contains_markdown_table(text):
        return True
    return any(re.search(pattern, text, re.MULTILINE) for pattern in _MARKDOWN_PATTERNS)


def normalize_markdown_for_channel(text: str, channel_name: str | None = None) -> str:
    if not text:
        return ""
    normalized = _normalize_markdown_tables(text, channel_name=channel_name)
    return normalized.strip()


def _contains_markdown_table(text: str) -> bool:
    lines = text.splitlines()
    for index in range(len(lines) - 1):
        if "|" not in lines[index]:
            continue
        if _TABLE_SEPARATOR_RE.match(lines[index + 1] or ""):
            return True
    return False


def _normalize_markdown_tables(text: str, channel_name: str | None = None) -> str:
    lines = text.splitlines()
    result: list[str] = []
    index = 0
    while index < len(lines):
        table_block, next_index = _consume_table_block(lines, index)
        if table_block is None:
            result.append(lines[index])
            index += 1
            continue
        if result and result[-1].strip():
            result.append("")
        result.extend(_render_table_block(table_block, channel_name=channel_name))
        if next_index < len(lines) and lines[next_index].strip():
            result.append("")
        index = next_index
    return "\n".join(result)


def _consume_table_block(lines: list[str], start_index: int) -> tuple[list[str] | None, int]:
    if start_index + 1 >= len(lines):
        return None, start_index
    header = lines[start_index]
    separator = lines[start_index + 1]
    if "|" not in header or not _TABLE_SEPARATOR_RE.match(separator or ""):
        return None, start_index

    block = [header, separator]
    index = start_index + 2
    while index < len(lines):
        current = lines[index]
        if "|" not in current or not current.strip():
            break
        block.append(current)
        index += 1
    return block, index


def _split_table_row(line: str) -> list[str]:
    working = line.strip()
    if working.startswith("|"):
        working = working[1:]
    if working.endswith("|"):
        working = working[:-1]
    return [cell.strip() for cell in working.split("|")]


def _render_table_block(lines: list[str], channel_name: str | None = None) -> list[str]:
    headers = _split_table_row(lines[0])
    data_rows = [_split_table_row(line) for line in lines[2:]]
    if not headers or not data_rows:
        return lines
    if _is_dingtalk_channel(channel_name):
        return _render_table_block_for_dingtalk(headers, data_rows)

    rendered: list[str] = []
    for row_index, row in enumerate(data_rows, start=1):
        cells: list[str] = []
        for column_index, header in enumerate(headers):
            value = row[column_index] if column_index < len(row) else ""
            if not value:
                continue
            cells.append(f"{header}: {value}")
        if not cells:
            continue
        rendered.append(f"{row_index}. " + " | ".join(cells))
    return rendered or lines


def _is_dingtalk_channel(channel_name: str | None) -> bool:
    return str(channel_name or "").lower().startswith("dingtalk")


def _render_table_block_for_dingtalk(headers: list[str], data_rows: list[list[str]]) -> list[str]:
    rendered: list[str] = []
    for row_index, row in enumerate(data_rows, start=1):
        cells: list[str] = []
        for column_index, header in enumerate(headers):
            value = row[column_index] if column_index < len(row) else ""
            value = value.strip()
            if not value:
                continue
            cells.append(f"- {header}：{value}")
        if not cells:
            continue
        rendered.append(f"{row_index}.")
        rendered.extend(cells)
        rendered.append("")
    while rendered and not rendered[-1].strip():
        rendered.pop()
    return rendered or data_rows
