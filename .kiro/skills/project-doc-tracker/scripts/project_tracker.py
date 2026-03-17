from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
from typing import Iterable


TRACKER_DIR = Path("docs") / "project-tracker"
FEATURES_DIR = TRACKER_DIR / "features"
ITEM_HEADERS = [
    "feature_id",
    "标题",
    "状态",
    "最近更新",
    "下一步",
    "关键文件",
    "正式文档",
]
PLACEHOLDER_TEXT = {"待补充", "暂无", "无", "-", "None"}
FEATURE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

OVERVIEW_TEMPLATE = """# Project Tracker

## 项目简介
<!-- project-tracker:intro:start -->
待补充。
<!-- project-tracker:intro:end -->

## 当前活跃事项
<!-- project-tracker:items:start -->
| feature_id | 标题 | 状态 | 最近更新 | 下一步 | 关键文件 | 正式文档 |
| --- | --- | --- | --- | --- | --- | --- |
<!-- project-tracker:items:end -->

## 最近一次会话
<!-- project-tracker:session:start -->
待补充。
<!-- project-tracker:session:end -->

## 下一步建议
<!-- project-tracker:next:start -->
- 待补充
<!-- project-tracker:next:end -->

## 已知阻塞
<!-- project-tracker:blockers:start -->
- 暂无
<!-- project-tracker:blockers:end -->
"""

PROGRESS_TEMPLATE = "# Project Progress Log\n"

MARKERS = {
    "intro": ("<!-- project-tracker:intro:start -->", "<!-- project-tracker:intro:end -->"),
    "items": ("<!-- project-tracker:items:start -->", "<!-- project-tracker:items:end -->"),
    "session": ("<!-- project-tracker:session:start -->", "<!-- project-tracker:session:end -->"),
    "next": ("<!-- project-tracker:next:start -->", "<!-- project-tracker:next:end -->"),
    "blockers": ("<!-- project-tracker:blockers:start -->", "<!-- project-tracker:blockers:end -->"),
}


def project_root(value: str | None) -> Path:
    return Path(value).resolve() if value else Path.cwd()


def tracker_root(root: Path) -> Path:
    return root / TRACKER_DIR


def overview_path(root: Path) -> Path:
    return tracker_root(root) / "OVERVIEW.md"


def progress_path(root: Path) -> Path:
    return tracker_root(root) / "PROGRESS.md"


def feature_note_path(root: Path, feature_id: str) -> Path:
    return tracker_root(root) / "features" / f"{valid_feature_id(feature_id)}.md"


def now_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def valid_feature_id(value: str) -> str:
    cleaned = value.strip()
    if not FEATURE_ID_PATTERN.fullmatch(cleaned):
        raise argparse.ArgumentTypeError(
            "feature_id must be a slug-like identifier using only letters, numbers, '-' or '_'."
        )
    return cleaned


def normalize_text(value: str | None, fallback: str) -> str:
    if value is None:
        return fallback
    cleaned = " ".join(part.strip() for part in value.replace("\r", "\n").splitlines() if part.strip()).strip()
    return cleaned or fallback


def sanitize_cell(value: str | None, fallback: str = "-") -> str:
    cleaned = normalize_text(value, fallback).replace("|", "/")
    return cleaned or fallback


def render_markdown_bullets(items: Iterable[str] | None, fallback: str) -> str:
    if not items:
        return fallback
    cleaned = [normalize_text(item, "") for item in items if normalize_text(item, "")]
    return "\n".join(f"- {item}" for item in cleaned) if cleaned else fallback


def parse_markdown_bullets(section_body: str | None) -> list[str]:
    if not section_body:
        return []
    values: list[str] = []
    for raw_line in section_body.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            payload = line[2:].strip()
            if payload and payload not in PLACEHOLDER_TEXT:
                values.append(payload)
    return values


def extract_section_body(content: str, heading: str) -> str | None:
    pattern = rf"(?ms)^## {re.escape(heading)}\n\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, content)
    if not match:
        return None
    return match.group(1).strip()


def format_files(files: Iterable[str]) -> str:
    cleaned = [sanitize_cell(item, "") for item in files if sanitize_cell(item, "")]
    return ", ".join(cleaned) if cleaned else "无"


def ensure_initialized(root: Path) -> None:
    base = tracker_root(root)
    features = root / FEATURES_DIR
    base.mkdir(parents=True, exist_ok=True)
    features.mkdir(parents=True, exist_ok=True)
    if not overview_path(root).exists():
        overview_path(root).write_text(OVERVIEW_TEMPLATE, encoding="utf-8")
    if not progress_path(root).exists():
        progress_path(root).write_text(PROGRESS_TEMPLATE, encoding="utf-8")


def extract_marker_body(content: str, key: str) -> str:
    start, end = MARKERS[key]
    if start not in content or end not in content:
        raise ValueError(f"Missing marker block for {key}")
    _, rest = content.split(start, 1)
    body, _ = rest.split(end, 1)
    return body.strip("\n")


def replace_marker_block(content: str, key: str, new_body: str) -> str:
    start, end = MARKERS[key]
    if start not in content or end not in content:
        raise ValueError(f"Missing marker block for {key}")
    prefix, rest = content.split(start, 1)
    _, suffix = rest.split(end, 1)
    body = f"{start}\n{new_body.rstrip()}\n{end}"
    return prefix + body + suffix


def parse_table_rows(table_body: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in table_body.splitlines() if line.strip()]
    if len(lines) <= 2:
        return []

    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        if not line.startswith("|"):
            continue
        parts = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(parts) < len(ITEM_HEADERS):
            continue
        rows.append(dict(zip(ITEM_HEADERS, parts[: len(ITEM_HEADERS)])))
    return rows


def render_table_rows(rows: list[dict[str, str]]) -> str:
    lines = [
        "| feature_id | 标题 | 状态 | 最近更新 | 下一步 | 关键文件 | 正式文档 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                sanitize_cell(
                    row.get(header),
                    "无" if header == "关键文件" else "-",
                )
                for header in ITEM_HEADERS
            )
            + " |"
        )
    return "\n".join(lines)


def parse_keyed_bullets(body: str) -> tuple[list[tuple[str, str]], list[str]]:
    keyed: list[tuple[str, str]] = []
    extras: list[str] = []

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        payload = line[2:].strip()
        if not payload or payload in PLACEHOLDER_TEXT:
            continue
        if ": " in payload:
            key, value = payload.split(": ", 1)
            if key and value:
                keyed.append((key.strip(), normalize_text(value, "待补充")))
                continue
        extras.append(payload)
    return keyed, extras


def render_keyed_bullets(
    keyed: list[tuple[str, str]],
    extras: list[str],
    *,
    default_text: str,
) -> str:
    lines = [f"- {key}: {value}" for key, value in keyed]
    lines.extend(f"- {value}" for value in extras)
    if not lines:
        return f"- {default_text}"
    return "\n".join(lines)


def upsert_feature_bullet_block(
    content: str,
    key: str,
    feature_id: str,
    value: str | None,
    *,
    default_text: str,
    drop_when_empty: bool,
) -> str:
    keyed, extras = parse_keyed_bullets(extract_marker_body(content, key))

    ordered: list[tuple[str, str]] = []
    seen = False
    cleaned_value = normalize_text(value, "") if value else ""
    should_keep = bool(cleaned_value and cleaned_value not in PLACEHOLDER_TEXT)

    for existing_key, existing_value in keyed:
        if existing_key == feature_id:
            seen = True
            if should_keep:
                ordered.append((feature_id, cleaned_value))
            elif not drop_when_empty:
                ordered.append((feature_id, existing_value))
        else:
            ordered.append((existing_key, existing_value))

    if not seen and should_keep:
        ordered.append((feature_id, cleaned_value))

    new_body = render_keyed_bullets(ordered, extras, default_text=default_text)
    return replace_marker_block(content, key, new_body)


def append_log(
    root: Path,
    change_type: str,
    summary: str,
    feature_id: str | None,
    files: Iterable[str],
    next_step: str | None,
    blockers: str | None,
    confidence: str,
) -> Path:
    ensure_initialized(root)
    resolved_feature_id = valid_feature_id(feature_id) if feature_id else "unknown"
    note = [
        "",
        f"## {now_timestamp()}",
        f"- change_type: {sanitize_cell(change_type)}",
        f"- feature_id: {sanitize_cell(resolved_feature_id)}",
        f"- summary: {sanitize_cell(summary)}",
        f"- files: {format_files(files)}",
        f"- next_step: {sanitize_cell(next_step, '待补充')}",
        f"- blockers: {sanitize_cell(blockers, '无')}",
        f"- confidence: {sanitize_cell(confidence, 'medium')}",
        "",
    ]
    with progress_path(root).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(note))
    return progress_path(root)


def sync_item(
    root: Path,
    feature_id: str,
    title: str,
    status: str,
    summary: str,
    next_step: str,
    files: Iterable[str],
    blockers: str | None,
    formal_doc: str | None = None,
) -> Path:
    ensure_initialized(root)
    feature_id = valid_feature_id(feature_id)
    target = overview_path(root)
    content = target.read_text(encoding="utf-8")

    rows = parse_table_rows(extract_marker_body(content, "items"))
    existing_row = next((row for row in rows if row.get("feature_id") == feature_id), None)
    resolved_formal_doc = formal_doc
    if resolved_formal_doc is None and existing_row:
        existing_formal_doc = existing_row.get("正式文档", "").strip()
        if existing_formal_doc and existing_formal_doc != "-":
            resolved_formal_doc = existing_formal_doc

    updated_row = {
        "feature_id": sanitize_cell(feature_id),
        "标题": sanitize_cell(title),
        "状态": sanitize_cell(status),
        "最近更新": now_timestamp(),
        "下一步": sanitize_cell(next_step),
        "关键文件": format_files(files),
        "正式文档": sanitize_cell(resolved_formal_doc, "-"),
    }

    merged = False
    for index, row in enumerate(rows):
        if row.get("feature_id") == feature_id:
            rows[index] = updated_row
            merged = True
            break

    if not merged:
        rows.append(updated_row)

    content = replace_marker_block(content, "items", render_table_rows(rows))
    content = replace_marker_block(content, "session", normalize_text(summary, "待补充。"))
    content = upsert_feature_bullet_block(
        content,
        "next",
        feature_id,
        next_step,
        default_text="待补充",
        drop_when_empty=False,
    )
    content = upsert_feature_bullet_block(
        content,
        "blockers",
        feature_id,
        blockers,
        default_text="暂无",
        drop_when_empty=True,
    )
    target.write_text(content, encoding="utf-8")
    return target


def write_feature_note(
    root: Path,
    feature_id: str,
    title: str,
    status: str,
    background: str,
    implementation: str,
    next_step: str,
    files: Iterable[str],
    risks: str | None,
    evidence: Iterable[str] | None = None,
    related_docs: Iterable[str] | None = None,
    formal_doc: str | None = None,
) -> Path:
    ensure_initialized(root)
    feature_id = valid_feature_id(feature_id)
    target = feature_note_path(root, feature_id)
    existing_content = target.read_text(encoding="utf-8") if target.exists() else ""
    file_lines = "\n".join(f"- {item}" for item in files) if files else "- 无"
    resolved_evidence = list(evidence) if evidence is not None else parse_markdown_bullets(
        extract_section_body(existing_content, "状态判断依据")
    )
    resolved_related_docs = list(related_docs) if related_docs is not None else parse_markdown_bullets(
        extract_section_body(existing_content, "相关文档")
    )
    resolved_formal_doc = formal_doc
    if resolved_formal_doc is None:
        existing_formal_doc = extract_section_body(existing_content, "正式文档")
        if existing_formal_doc and existing_formal_doc not in PLACEHOLDER_TEXT:
            resolved_formal_doc = existing_formal_doc
    content = f"""# Feature Note: {feature_id}

- feature_id: {feature_id}
- title: {title}
- updated_at: {now_timestamp()}
- status: {status}

## 背景

{background}

## 当前实现摘要

{implementation}

## 状态判断依据

{render_markdown_bullets(resolved_evidence, '待补充')}

## 关键文件

{file_lines}

## 相关文档

{render_markdown_bullets(resolved_related_docs, '待补充')}

## 风险与已知问题

{risks or '暂无'}

## 后续建议

{next_step}

## 正式文档

{resolved_formal_doc or '待补充'}
"""
    target.write_text(content, encoding="utf-8")
    return target


def show_status(root: Path, limit: int) -> str:
    ensure_initialized(root)
    overview = overview_path(root).read_text(encoding="utf-8").rstrip()
    progress_lines = progress_path(root).read_text(encoding="utf-8").splitlines()
    headings = [idx for idx, line in enumerate(progress_lines) if line.startswith("## ")]
    if not headings:
        tail = "# Recent Progress\n\n暂无记录。"
    else:
        start = headings[max(len(headings) - limit, 0)]
        tail = "# Recent Progress\n\n" + "\n".join(progress_lines[start:]).strip()
    return overview + "\n\n" + tail + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project tracker helper for the project-doc-tracker skill.")
    parser.add_argument("--project-root", dest="project_root", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init")

    log_parser = subparsers.add_parser("log")
    log_parser.add_argument("--change-type", required=True)
    log_parser.add_argument("--summary", required=True)
    log_parser.add_argument("--feature-id", type=valid_feature_id)
    log_parser.add_argument("--file", action="append", default=[])
    log_parser.add_argument("--next-step")
    log_parser.add_argument("--blockers")
    log_parser.add_argument("--confidence", default="medium")

    item_parser = subparsers.add_parser("sync-item")
    item_parser.add_argument("--feature-id", required=True, type=valid_feature_id)
    item_parser.add_argument("--title", required=True)
    item_parser.add_argument("--status", required=True)
    item_parser.add_argument("--summary", required=True)
    item_parser.add_argument("--next-step", required=True)
    item_parser.add_argument("--file", action="append", default=[])
    item_parser.add_argument("--blockers")
    item_parser.add_argument("--formal-doc")

    feature_parser = subparsers.add_parser("feature-note")
    feature_parser.add_argument("--feature-id", required=True, type=valid_feature_id)
    feature_parser.add_argument("--title", required=True)
    feature_parser.add_argument("--status", required=True)
    feature_parser.add_argument("--background", required=True)
    feature_parser.add_argument("--implementation", required=True)
    feature_parser.add_argument("--next-step", required=True)
    feature_parser.add_argument("--file", action="append", default=[])
    feature_parser.add_argument("--risks")
    feature_parser.add_argument("--evidence", action="append")
    feature_parser.add_argument("--related-doc", action="append")
    feature_parser.add_argument("--formal-doc")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--limit", type=int, default=5)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = project_root(args.project_root)

    if args.command == "init":
        ensure_initialized(root)
        print(tracker_root(root))
        return 0

    if args.command == "log":
        target = append_log(
            root=root,
            change_type=args.change_type,
            summary=args.summary,
            feature_id=args.feature_id,
            files=args.file,
            next_step=args.next_step,
            blockers=args.blockers,
            confidence=args.confidence,
        )
        print(target)
        return 0

    if args.command == "sync-item":
        target = sync_item(
            root=root,
            feature_id=args.feature_id,
            title=args.title,
            status=args.status,
            summary=args.summary,
            next_step=args.next_step,
            files=args.file,
            blockers=args.blockers,
            formal_doc=args.formal_doc,
        )
        print(target)
        return 0

    if args.command == "feature-note":
        target = write_feature_note(
            root=root,
            feature_id=args.feature_id,
            title=args.title,
            status=args.status,
            background=args.background,
            implementation=args.implementation,
            next_step=args.next_step,
            files=args.file,
            risks=args.risks,
            evidence=args.evidence,
            related_docs=args.related_doc,
            formal_doc=args.formal_doc,
        )
        print(target)
        return 0

    if args.command == "status":
        print(show_status(root, args.limit))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
