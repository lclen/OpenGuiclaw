from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def load_module(file_name: str, module_name: str):
    script_path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


project_tracker = load_module("project_tracker.py", "project_tracker")
setup_kiro_steering = load_module("setup_kiro_steering.py", "setup_kiro_steering")
setup_tool_rules = load_module("setup_tool_rules.py", "setup_tool_rules")


class ProjectTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        project_tracker.ensure_initialized(self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sync_item_preserves_existing_formal_doc_when_not_provided(self) -> None:
        project_tracker.sync_item(
            root=self.root,
            feature_id="alpha",
            title="Alpha",
            status="done",
            summary="first pass",
            next_step="keep doc",
            files=["src/alpha.py"],
            blockers=None,
            formal_doc="docs/modules/alpha.md",
        )

        project_tracker.sync_item(
            root=self.root,
            feature_id="alpha",
            title="Alpha",
            status="done",
            summary="second pass",
            next_step="still keep doc",
            files=["src/alpha.py"],
            blockers=None,
            formal_doc=None,
        )

        overview = project_tracker.overview_path(self.root).read_text(encoding="utf-8")
        self.assertIn("docs/modules/alpha.md", overview)
        self.assertEqual(overview.count("docs/modules/alpha.md"), 1)
        self.assertIn("still keep doc", overview)

    def test_feature_note_rejects_path_traversal_feature_id(self) -> None:
        with self.assertRaises(SystemExit):
            parser = project_tracker.build_parser()
            parser.parse_args(
                [
                    "feature-note",
                    "--feature-id",
                    "..\\..\\outside-test",
                    "--title",
                    "Escape",
                    "--status",
                    "done",
                    "--background",
                    "b",
                    "--implementation",
                    "i",
                    "--next-step",
                    "n",
                ]
            )

    def test_feature_note_stays_inside_features_directory(self) -> None:
        target = project_tracker.write_feature_note(
            root=self.root,
            feature_id="alpha_note",
            title="Alpha",
            status="done",
            background="background",
            implementation="implementation",
            next_step="next",
            files=[],
            risks=None,
            formal_doc=None,
        )

        self.assertEqual(target.parent, project_tracker.tracker_root(self.root) / "features")
        self.assertTrue(target.exists())

    def test_feature_note_preserves_formal_doc_and_supports_richer_sections(self) -> None:
        project_tracker.write_feature_note(
            root=self.root,
            feature_id="alpha-note",
            title="Alpha",
            status="in_progress",
            background="background",
            implementation="implementation",
            next_step="next",
            files=["src/alpha.py"],
            risks="risk",
            evidence=["Updated src/alpha.py", "Captured the tracker record"],
            related_docs=["docs/specs/alpha.md"],
            formal_doc="docs/modules/alpha.md",
        )

        project_tracker.write_feature_note(
            root=self.root,
            feature_id="alpha-note",
            title="Alpha",
            status="done",
            background="updated background",
            implementation="updated implementation",
            next_step="publish",
            files=["src/alpha.py"],
            risks="low risk",
            evidence=None,
            related_docs=None,
            formal_doc=None,
        )

        note = project_tracker.feature_note_path(self.root, "alpha-note").read_text(encoding="utf-8")
        self.assertIn("## 状态判断依据", note)
        self.assertIn("- Updated src/alpha.py", note)
        self.assertIn("## 相关文档", note)
        self.assertIn("- docs/specs/alpha.md", note)
        self.assertIn("docs/modules/alpha.md", note)

    def test_setup_kiro_steering_installs_only_the_copy_block(self) -> None:
        target = setup_kiro_steering.install_steering(self.root, force=False)
        content = target.read_text(encoding="utf-8")

        self.assertTrue(target.exists())
        self.assertIn("## Project Progress Tracking Rules", content)
        self.assertNotIn("# Steering Template: project-doc-tracker", content)

    def test_setup_tool_rules_installs_cursor_and_codex_targets(self) -> None:
        cursor_target = setup_tool_rules.install_rule(self.root, "cursor", force=False)
        codex_target = setup_tool_rules.install_rule(self.root, "codex", force=False)

        self.assertEqual(cursor_target, self.root / ".cursorrules")
        self.assertEqual(codex_target, self.root / "AGENTS.md")
        self.assertIn("## Project Progress Tracking Rules", cursor_target.read_text(encoding="utf-8"))
        self.assertIn("## Project Progress Tracking Rules", codex_target.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
