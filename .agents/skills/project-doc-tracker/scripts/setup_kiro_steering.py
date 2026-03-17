from __future__ import annotations

from pathlib import Path

from setup_tool_rules import install_rule, project_root, run_installer


def install_steering(root: Path, *, force: bool) -> Path:
    return install_rule(root, "kiro", force=force)


def main() -> int:
    return run_installer("kiro", "Install the project-doc-tracker steering file into a target Kiro project.")


if __name__ == "__main__":
    raise SystemExit(main())
