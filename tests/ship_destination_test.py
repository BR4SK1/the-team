#!/usr/bin/env python3
"""Fixture tests for scripts/ship/ship-destination (Step 2 selection).

Uses only local Git repositories with GitHub-style remote URL strings
in config (no fetch, no push, no network, no live remotes). The helper
is read-only, so these fixtures never contact the configured URL.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER = REPO_ROOT / "scripts" / "ship" / "ship-destination"
GITHUB_URL = "https://github.com/example/fixture.git"


def run(args, cwd=None):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=30
    )


def git(repo, *args):
    proc = run(["git", "-C", str(repo), *args])
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {proc.stdout} {proc.stderr}")
    return proc.stdout.strip()


def make_repo(base, *, branch="main", remotes=None):
    work = base / "work"
    work.mkdir(parents=True)
    run(["git", "init", "-q", "-b", "main", str(work)])
    git(work, "config", "user.email", "fixture@example.invalid")
    git(work, "config", "user.name", "Fixture")
    (work / "file.txt").write_text("initial\n", encoding="utf-8")
    git(work, "add", "file.txt")
    git(work, "commit", "-q", "-m", "initial")
    for name, url in (remotes or {}).items():
        git(work, "remote", "add", name, url)
    if branch != "main":
        git(work, "switch", "-c", branch)
    return work


def stage(work, path="file.txt", text="changed\n"):
    target = work / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git(work, "add", path)


def decide(work, *extra):
    proc = run([str(HELPER), str(work), *extra])
    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        raise AssertionError(
            f"helper did not emit JSON: rc={proc.returncode} "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        ) from exc
    return proc.returncode, payload


class ShipDestinationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_normal_unique_remote_off_main(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        stage(work)
        rc, payload = decide(work)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["status"], "selected")
        self.assertEqual(payload["remote"], "origin")
        self.assertEqual(payload["topic"], "feat/topic")
        self.assertEqual(payload["ref"], "refs/heads/feat/topic")
        self.assertEqual(payload["github"], {"owner": "example", "repo": "fixture"})
        self.assertEqual(payload["selection"], "current_branch/single_remote")
        # The helper suggests no commit message; the skill (Step 3)
        # requires a meaningful Conventional Commit.
        self.assertIsNone(payload["suggested_message"])
        self.assertNotIn("ship:", json.dumps(payload))
        self.assertEqual(payload["staged_files"], ["file.txt"])

    def test_off_main_upstream_resolves_multiple_remotes(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL,
                                  "upstream2": "https://github.com/example/other.git"})
        git(work, "config", "branch.feat/topic.remote", "upstream2")
        git(work, "config", "branch.feat/topic.merge", "refs/heads/feat/topic")
        stage(work)
        rc, payload = decide(work)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["remote"], "upstream2")
        self.assertEqual(payload["selection"], "current_branch/upstream")

    def test_on_main_derives_unique_topic_from_staged_change(self):
        work = make_repo(self.base, remotes={"origin": GITHUB_URL})
        stage(work, "fleet/skills/ship/SKILL.md")
        rc, payload = decide(work)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["topic"], "ship/fleet-skills-ship-skill")
        self.assertEqual(payload["ref"], "refs/heads/ship/fleet-skills-ship-skill")
        self.assertEqual(payload["selection"], "derived_on_main/single_remote")
        # A pre-existing local branch forces the -2 suffix (uniqueness).
        git(work, "branch", "ship/fleet-skills-ship-skill")
        rc2, payload2 = decide(work)
        self.assertEqual(rc2, 0)
        self.assertEqual(payload2["topic"], "ship/fleet-skills-ship-skill-2")

    def test_on_main_main_tracking_resolves_multiple_remotes(self):
        work = make_repo(self.base, remotes={"origin": GITHUB_URL,
                                             "mainremote": "https://github.com/example/main.git"})
        git(work, "config", "branch.main.remote", "mainremote")
        stage(work)
        rc, payload = decide(work)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["remote"], "mainremote")
        self.assertEqual(payload["selection"], "derived_on_main/main_tracking")

    def test_explicit_remote_and_branch_on_main(self):
        work = make_repo(self.base, remotes={"origin": GITHUB_URL,
                                             "other": "https://github.com/example/other.git"})
        stage(work)
        rc, payload = decide(work, "--remote", "other", "--branch", "ship/explicit")
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["remote"], "other")
        self.assertEqual(payload["topic"], "ship/explicit")
        self.assertEqual(payload["selection"], "explicit/explicit")

    def test_conflict_explicit_branch_mismatch_off_main(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        stage(work)
        rc, payload = decide(work, "--branch", "feat/other")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "explicit_branch_conflict")

    def test_conflict_ambiguous_multiple_remotes(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL,
                                  "other": "https://github.com/example/other.git"})
        stage(work)
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "ambiguous_remote")
        self.assertIsNone(payload["remote"])

    def test_conflict_upstream_mismatch(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        git(work, "config", "branch.feat/topic.remote", "origin")
        git(work, "config", "branch.feat/topic.merge", "refs/heads/feat/other")
        stage(work)
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "upstream_mismatch")

    def test_conflict_pushurl_divert_blocks(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        git(work, "config", "remote.origin.pushurl", "https://github.com/example/divert.git")
        stage(work)
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "ineligible_remote")

    def test_non_github_remote_identity_unverified(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": "/srv/git/fixture.git"})
        stage(work)
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "github_identity_unverified")
        # No raw URL is emitted.
        self.assertNotIn("/srv/git", json.dumps(payload))

    def test_empty_staged_is_scope_blocker(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "staged_empty")
        self.assertTrue(payload["scope"]["staged_empty"])

    def test_unstaged_and_untracked_are_scope_blockers(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        stage(work)
        (work / "file.txt").write_text("unstaged\n", encoding="utf-8")
        (work / "untracked.txt").write_text("payload\n", encoding="utf-8")
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "scope_unclean")

    def test_detached_head_blocks(self):
        work = make_repo(self.base, remotes={"origin": GITHUB_URL})
        head = git(work, "rev-parse", "HEAD")
        git(work, "switch", "-q", "--detach", head)
        stage(work)
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "detached_head")

    def test_helper_is_read_only_shape(self):
        text = HELPER.read_text(encoding="utf-8")
        for banned in ("os.system", "os.popen", "os.exec", "urllib", "socket"):
            self.assertNotIn(banned, text)
        # Mutating Git subcommands are never invoked; they may only
        # appear in prose. Check the actual git() call sites instead.
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith('git(repo, "'):
                for mutating in ('"push"', '"fetch"', '"commit"', '"switch"',
                                 '"update-ref"', '"merge"'):
                    self.assertNotIn(mutating, stripped)
        self.assertIn("--no-optional-locks", text)
        self.assertIn("branch.{branch}.remote", text)
        self.assertIn("never emits a raw remote URL", text)


if __name__ == "__main__":
    unittest.main()
