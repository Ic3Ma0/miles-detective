#!/usr/bin/env python3
"""Behaviour tests for scripts/package.py."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import package


class CollectFilesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for relative in ("SKILL.md", "README.md", "references/a.md",
                         "scripts/research_log.py", "scripts/package.py",
                         "scripts/test_package.py", "docs/agents/x.md",
                         "evals/README.md", "examples/case/outputs/report.md",
                         "CLAUDE.md", ".gitignore", ".DS_Store", "__pycache__/x.pyc"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_collects_skill_files_and_excludes_workspace_files(self):
        names = {path.as_posix() for path in package.collect_files(self.root)}
        self.assertIn("SKILL.md", names)
        self.assertIn("references/a.md", names)
        self.assertIn("scripts/research_log.py", names)
        self.assertNotIn("scripts/package.py", names)
        self.assertNotIn("scripts/test_package.py", names)
        self.assertNotIn("docs/agents/x.md", names)
        self.assertNotIn("evals/README.md", names)
        self.assertNotIn("examples/case/outputs/report.md", names)
        self.assertNotIn("CLAUDE.md", names)
        self.assertNotIn(".gitignore", names)
        self.assertNotIn(".DS_Store", names)
        self.assertNotIn("__pycache__/x.pyc", names)


class BuildAndIndexTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        (self.root / "references").mkdir(parents=True)
        (self.root / "SKILL.md").write_text("skill", encoding="utf-8")
        (self.root / "references" / "a.md").write_text("ref", encoding="utf-8")
        self.output = Path(self.temp.name) / "outputs"

    def tearDown(self):
        self.temp.cleanup()

    def test_zip_has_top_level_directory_and_no_excluded_files(self):
        files = package.collect_files(self.root)
        zip_path = self.output / "pkg.zip"
        count, size, digest = package.build_zip(self.root, files, zip_path)
        self.assertEqual(count, 2)
        self.assertGreater(size, 0)
        self.assertEqual(len(digest), 64)
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
        self.assertEqual(names, {"miles-detective/SKILL.md", "miles-detective/references/a.md"})

    def test_index_marks_previous_package_superseded(self):
        index_path = self.output / package.INDEX_NAME
        package.update_index(index_path, "Miles-侦探-Skill-r9.zip", 17, 57914, "a" * 64)
        entry, previous = package.update_index(
            index_path, "Miles-侦探-Skill-r10.zip", 18, 60000, "b" * 64, "~/.claude/skills/miles-detective")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(previous, "Miles-侦探-Skill-r9.zip")
        self.assertEqual(index["Miles-侦探-Skill-r9.zip"]["superseded_by"], "Miles-侦探-Skill-r10.zip")
        self.assertEqual(index["Miles-侦探-Skill-r10.zip"]["supersedes"], "Miles-侦探-Skill-r9.zip")
        self.assertEqual(entry["installed_to"], "~/.claude/skills/miles-detective")

    def test_current_package_ignores_superseded_entries(self):
        index = {
            "Miles-侦探-Skill-r8.zip": {"superseded_by": "Miles-侦探-Skill-r9.zip"},
            "Miles-侦探-Skill-r9.zip": {},
            "Miles-孙宇晨-R002-研究资料包.zip": {},
        }
        self.assertEqual(package.current_package(index), "Miles-侦探-Skill-r9.zip")


if __name__ == "__main__":
    unittest.main()
