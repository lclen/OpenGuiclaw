from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / ".agents" / "skills"
PACKAGE_ROOT = ROOT / "publish" / "project-docs-skills"
README_TEMPLATE = ROOT / "publish" / "project-docs-skills.README.md"
LICENSE_TEMPLATE = ROOT / "publish" / "project-docs-skills.LICENSE"
SKILLS = ["project-doc-tracker", "professional-markdown"]
IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc")


def reset_package_root() -> None:
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for child in PACKAGE_ROOT.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def main() -> int:
    reset_package_root()

    for skill_name in SKILLS:
        source = SOURCE_ROOT / skill_name
        target = PACKAGE_ROOT / skill_name
        if not source.exists():
            raise FileNotFoundError(f"Missing skill source: {source}")
        shutil.copytree(source, target, ignore=IGNORE_PATTERNS)

    if not README_TEMPLATE.exists():
        raise FileNotFoundError(f"Missing package README template: {README_TEMPLATE}")
    shutil.copy2(README_TEMPLATE, PACKAGE_ROOT / "README.md")
    if not LICENSE_TEMPLATE.exists():
        raise FileNotFoundError(f"Missing package license template: {LICENSE_TEMPLATE}")
    shutil.copy2(LICENSE_TEMPLATE, PACKAGE_ROOT / "LICENSE")

    print(PACKAGE_ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
