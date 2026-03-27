from __future__ import annotations

import ast
import io
import itertools
import logging
import os
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from core.automation_context import get_request_workspace_path

logger = logging.getLogger(__name__)

_HYPHEN_SPACING_RE = re.compile(r"\s*-\s*")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass
class ToolPathResolution:
    original_path: str
    resolved_path: str
    was_repaired: bool = False
    repair_reason: str | None = None
    candidates: list[str] = field(default_factory=list)


def _path_exists(candidate: Path, expect: str) -> bool:
    if expect == "file":
        return candidate.is_file()
    if expect == "dir":
        return candidate.is_dir()
    if expect == "parent":
        return candidate.parent.exists()
    return candidate.exists()


def _normalize_raw_path(path: str) -> str:
    text = (path or "").strip()
    text = text.replace("／", "/").replace("＼", "\\")
    text = re.sub(r"[\\/]+", lambda match: "\\" if "\\" in match.group(0) else "/", text)
    return text.rstrip("\\/") if len(text) > 3 else text


def _split_raw_path(path: str) -> tuple[str, list[str], bool]:
    normalized = _normalize_raw_path(path)
    drive, rest = os.path.splitdrive(normalized)
    is_absolute = bool(drive) or normalized.startswith(("\\", "/"))
    rest = rest.lstrip("\\/")
    parts = [segment for segment in re.split(r"[\\/]+", rest) if segment]
    return drive, parts, is_absolute


def _segment_variants(segment: str) -> list[str]:
    candidates: list[str] = []
    for value in (
        segment,
        segment.strip(),
        _HYPHEN_SPACING_RE.sub("-", segment.strip()),
    ):
        if value and value not in candidates:
            candidates.append(value)
    return candidates or [segment]


def _compose_path(drive: str, parts: Iterable[str], is_absolute: bool) -> str:
    parts_list = list(parts)
    if os.name == "nt":
        prefix = drive
        if is_absolute:
            prefix = f"{prefix}\\" if drive else "\\"
        if parts_list:
            return f"{prefix}{'\\\\'.join(parts_list)}" if prefix else "\\".join(parts_list)
        return prefix or "."
    prefix = "/" if is_absolute else ""
    return prefix + "/".join(parts_list)


def _candidate_strings(path: str) -> list[str]:
    drive, parts, is_absolute = _split_raw_path(path)
    if not parts:
        normalized = _normalize_raw_path(path)
        return [normalized] if normalized else []
    per_segment = [_segment_variants(segment) for segment in parts]
    candidates: list[str] = []
    for combo in itertools.product(*per_segment):
        candidate = _compose_path(drive, combo, is_absolute)
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _effective_workspace_root(workspace_path: str | None = None) -> Path | None:
    current = workspace_path or get_request_workspace_path()
    return Path(current) if current else None


def _existing_candidates(
    path: str,
    *,
    cwd: str | Path | None = None,
    workspace_path: str | None = None,
    expect: str = "any",
) -> list[Path]:
    normalized = _normalize_raw_path(path)
    raw_candidate = Path(normalized)
    bases: list[Path | None] = []
    workspace_root = _effective_workspace_root(workspace_path)
    if raw_candidate.is_absolute():
        bases.append(None)
    else:
        if cwd:
            bases.append(Path(cwd))
        if workspace_root and workspace_root not in bases:
            bases.append(workspace_root)
        current_dir = Path.cwd()
        if current_dir not in bases:
            bases.append(current_dir)

    matches: list[Path] = []
    for base in bases or [None]:
        for candidate_text in _candidate_strings(normalized):
            candidate_path = Path(candidate_text)
            if not candidate_path.is_absolute() and base is not None:
                candidate_path = base / candidate_path
            candidate_path = candidate_path.resolve(strict=False)
            if _path_exists(candidate_path, expect) and candidate_path not in matches:
                matches.append(candidate_path)
    return matches


def resolve_tool_path(
    path: str,
    *,
    cwd: str | Path | None = None,
    workspace_path: str | None = None,
    expect: str = "any",
) -> ToolPathResolution:
    original = path or ""
    normalized = _normalize_raw_path(original)
    direct = Path(normalized)
    if not direct.is_absolute():
        base_root = _effective_workspace_root(workspace_path) or (Path(cwd) if cwd else Path.cwd())
        direct = (base_root / direct).resolve(strict=False)
    else:
        direct = direct.resolve(strict=False)

    if _path_exists(direct, expect):
        return ToolPathResolution(
            original_path=original,
            resolved_path=str(direct),
        )

    candidates = _existing_candidates(
        normalized,
        cwd=cwd,
        workspace_path=workspace_path,
        expect=expect,
    )
    candidate_strings = [str(candidate) for candidate in candidates]
    if len(candidate_strings) == 1:
        reason_parts: list[str] = []
        if normalized != original:
            reason_parts.append("trim/slash")
        if _HYPHEN_SPACING_RE.sub("-", original) != original:
            reason_parts.append("hyphen-spacing")
        if not reason_parts:
            reason_parts.append("nearby-existing-path")
        repaired = candidate_strings[0]
        return ToolPathResolution(
            original_path=original,
            resolved_path=repaired,
            was_repaired=True,
            repair_reason="+".join(reason_parts),
            candidates=candidate_strings,
        )

    return ToolPathResolution(
        original_path=original,
        resolved_path=str(direct),
        was_repaired=False,
        repair_reason=None,
        candidates=candidate_strings,
    )


def format_repair_notice(result: ToolPathResolution) -> str:
    if not result.was_repaired:
        return ""
    return f"ℹ️ 已自动修正路径: {result.original_path} -> {result.resolved_path}"


def format_missing_path_message(result: ToolPathResolution, prefix: str) -> str:
    message = f"{prefix}: {result.original_path}"
    if result.candidates:
        if len(result.candidates) == 1:
            message += f"。建议路径: {result.candidates[0]}"
        else:
            message += "。存在多个候选路径，未自动替换: " + " | ".join(result.candidates[:5])
    return message


def log_path_resolution(
    *,
    tool_name: str,
    result: ToolPathResolution,
    cwd: str | Path | None = None,
    workspace_path: str | None = None,
) -> None:
    payload = {
        "tool": tool_name,
        "original_path": result.original_path,
        "resolved_path": result.resolved_path,
        "was_repaired": result.was_repaired,
        "repair_reason": result.repair_reason,
        "candidates": result.candidates,
        "cwd": str(cwd or ""),
        "workspace_path": workspace_path or get_request_workspace_path() or "",
    }
    if result.was_repaired:
        logger.info("[ToolPathRepair] %s", payload)
    elif result.candidates:
        logger.warning("[ToolPathRepair] ambiguous_or_missing %s", payload)


def repair_python_script_paths(
    script: str,
    *,
    cwd: str | Path | None = None,
    workspace_path: str | None = None,
) -> tuple[str, list[ToolPathResolution]]:
    if not script.strip():
        return script, []

    tokens = list(tokenize.generate_tokens(io.StringIO(script).readline))
    repaired: list[ToolPathResolution] = []
    updated_tokens = []

    for token in tokens:
        if token.type != tokenize.STRING:
            updated_tokens.append(token)
            continue
        try:
            literal_value = ast.literal_eval(token.string)
        except Exception:
            updated_tokens.append(token)
            continue
        if not isinstance(literal_value, str):
            updated_tokens.append(token)
            continue
        if not (_WINDOWS_DRIVE_RE.match(literal_value) or "/" in literal_value or "\\" in literal_value):
            updated_tokens.append(token)
            continue

        resolution = resolve_tool_path(
            literal_value,
            cwd=cwd,
            workspace_path=workspace_path,
            expect="any",
        )
        if resolution.was_repaired:
            repaired.append(resolution)
            token = tokenize.TokenInfo(
                token.type,
                repr(resolution.resolved_path),
                token.start,
                token.end,
                token.line,
            )
            log_path_resolution(
                tool_name="execute_python_script",
                result=resolution,
                cwd=cwd,
                workspace_path=workspace_path,
            )
        updated_tokens.append(token)

    return tokenize.untokenize(updated_tokens), repaired
