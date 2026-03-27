from core.runtime_deps import DependencySpec, ensure_runtime_dependencies


def test_ensure_runtime_dependencies_skips_install_when_ready(monkeypatch):
    monkeypatch.setattr("core.runtime_deps.dependency_is_ready", lambda spec: True)
    called = {"install": False}

    def fake_install(*packages):
        called["install"] = True
        return True

    monkeypatch.setattr("core.runtime_deps.auto_install_packages", fake_install)

    ok = ensure_runtime_dependencies(
        DependencySpec(module="json", package="json"),
        context="test",
    )

    assert ok is True
    assert called["install"] is False


def test_ensure_runtime_dependencies_installs_missing(monkeypatch):
    state = {"calls": 0}

    def fake_ready(spec):
        state["calls"] += 1
        return state["calls"] > 1

    installed = []

    monkeypatch.setattr("core.runtime_deps.dependency_is_ready", fake_ready)
    monkeypatch.setattr(
        "core.runtime_deps.auto_install_packages",
        lambda *packages: installed.extend(packages) is None or True,
    )

    ok = ensure_runtime_dependencies(
        DependencySpec(module="missing_mod", package="missing-pkg>=1.0", reason="missing"),
        context="test",
    )

    assert ok is True
    assert installed == ["missing-pkg>=1.0"]


def test_ensure_runtime_dependencies_returns_false_when_install_fails(monkeypatch):
    monkeypatch.setattr("core.runtime_deps.dependency_is_ready", lambda spec: False)
    monkeypatch.setattr("core.runtime_deps.auto_install_packages", lambda *packages: False)

    ok = ensure_runtime_dependencies(
        DependencySpec(module="missing_mod", package="missing-pkg>=1.0"),
        context="test",
    )

    assert ok is False
