"""Runtime dependency self-healing helpers."""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DependencySpec:
    module: str
    package: str
    version_check: Callable[[], bool] | None = None
    reason: str = ""


def installed_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def can_import(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


def dependency_is_ready(spec: DependencySpec) -> bool:
    if not can_import(spec.module):
        return False
    if spec.version_check is not None:
        try:
            return bool(spec.version_check())
        except Exception:
            return False
    return True


def auto_install_packages(*packages: str) -> bool:
    if not packages:
        return True
    command = [sys.executable, "-m", "pip", "install", *packages]
    logger.warning("[RuntimeDeps] Auto-fixing runtime dependency via: %s", " ".join(command))
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
    except Exception as exc:
        logger.error("[RuntimeDeps] Auto-install failed to start: %s", exc, exc_info=True)
        return False

    if result.returncode != 0:
        logger.error(
            "[RuntimeDeps] Auto-install failed code=%s stdout=%s stderr=%s",
            result.returncode,
            (result.stdout or "").strip()[-1000:],
            (result.stderr or "").strip()[-1000:],
        )
        return False

    logger.info("[RuntimeDeps] Auto-install finished stdout=%s", (result.stdout or "").strip()[-1000:])
    importlib.invalidate_caches()
    return True


def ensure_runtime_dependencies(*specs: DependencySpec, context: str = "runtime") -> bool:
    packages_to_install: list[str] = []

    for spec in specs:
        if dependency_is_ready(spec):
            continue
        reason = spec.reason or "missing or incompatible"
        logger.warning(
            "[RuntimeDeps] Dependency not ready context=%s module=%s package=%s reason=%s current_version=%s python=%s",
            context,
            spec.module,
            spec.package,
            reason,
            installed_version(spec.package),
            sys.executable,
        )
        packages_to_install.append(spec.package)

    if packages_to_install and not auto_install_packages(*packages_to_install):
        return False

    return all(dependency_is_ready(spec) for spec in specs)
