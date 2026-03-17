from __future__ import annotations

import argparse
from pathlib import Path


TOOL_TARGETS = {
    "kiro": ".kiro/steering/project-doc-tracker.md",
    "claude": "CLAUDE.md",
    "cursor": ".cursorrules",
    "windsurf": ".windsurfrules",
    "codex": "AGENTS.md",
}


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def project_root(value: str | None) -> Path:
    return Path(value).resolve() if value else Path.cwd()


def template_path(tool: str) -> Path:
    return skill_root() / "references" / "tool-rule-templates" / f"{tool}.md"


def target_path(root: Path, tool: str) -> Path:
    return root / Path(TOOL_TARGETS[tool])


def install_rule(root: Path, tool: str, *, force: bool) -> Path:
    template = template_path(tool)
    if not template.exists():
        raise FileNotFoundError(f"Missing template for tool '{tool}': {template}")

    target = target_path(root, tool)
    if target.exists() and not force:
        raise FileExistsError(f"Rule file already exists: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def add_common_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--force", action="store_true")
    return parser


def run_installer(tool: str, description: str) -> int:
    parser = add_common_arguments(argparse.ArgumentParser(description=description))
    args = parser.parse_args()
    target = install_rule(project_root(args.project_root), tool, force=args.force)
    print(target)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install project-doc-tracker rules into a target AI coding tool's project rule file."
    )
    parser.add_argument("--tool", choices=sorted(TOOL_TARGETS), required=True)
    return add_common_arguments(parser)


def main() -> int:
    args = build_parser().parse_args()
    target = install_rule(project_root(args.project_root), args.tool, force=args.force)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
