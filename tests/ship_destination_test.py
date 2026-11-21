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


def commit_candidate(work, path="file.txt", text="candidate\n"):
    target = work / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git(work, "add", path)
    git(work, "commit", "-q", "-m", "test: candidate")
    return git(work, "rev-parse", "HEAD")


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
        (work / "file.txt").write_text("changed\n", encoding="utf-8")
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "staged_empty")
        self.assertTrue(payload["scope"]["staged_empty"])
        # Off main the current branch is already the topic: the
        # ordinary staging path needs no proposal or switch.
        self.assertIsNone(payload["topic"])

    def test_empty_staged_on_main_reports_on_main_staged_empty(self):
        # Helper still reports staged_empty uniformly; eligibility of
        # the one-pass reviewed staging on main with established
        # task-owned provenance is a skill-level decision the helper
        # leaves to Caller. The helper surfaces on_main and scope.
        work = make_repo(self.base, remotes={"origin": GITHUB_URL})
        (work / "file.txt").write_text("changed\n", encoding="utf-8")
        (work / "new.txt").write_text("payload\n", encoding="utf-8")
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "staged_empty")
        self.assertTrue(payload["on_main"])
        self.assertIn("file.txt", payload["scope"]["unstaged"])
        self.assertIn("new.txt", payload["scope"]["untracked"])
        # Even while blocked, the proposal lets the caller branch
        # before staging: fully resolved remote/topic/github.
        self.assertTrue(payload["topic"].startswith("ship/"))
        self.assertNotEqual(payload["topic"], "main")
        self.assertEqual(payload["remote"], "origin")
        self.assertEqual(payload["github"], {"owner": "example", "repo": "fixture"})
        self.assertEqual(payload["ref"], f"refs/heads/{payload['topic']}")
        self.assertEqual(payload["selection"], "derived_on_main/single_remote")
        # Proposal is derived from the candidate work (first sorted
        # path is file.txt) before any staging.
        self.assertEqual(payload["topic"], "ship/file")
        # Topic does not already exist (duplicate-branch safety).
        self.assertEqual(
            run(["git", "-C", str(work), "show-ref", "--verify", "-q",
                 f"refs/heads/{payload['topic']}"]).returncode, 1)

    def test_empty_staged_on_main_explicit_branch_proposal(self):
        work = make_repo(self.base, remotes={"origin": GITHUB_URL})
        (work / "file.txt").write_text("changed\n", encoding="utf-8")
        rc, payload = decide(work, "--branch", "ship/explicit-proposal")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "staged_empty")
        self.assertEqual(payload["topic"], "ship/explicit-proposal")
        self.assertTrue(payload["on_main"])
        self.assertEqual(payload["selection"], "explicit/single_remote")

    def test_empty_staged_on_main_existing_branch_blocks_proposal(self):
        # An existing local topic must not be silently chosen again:
        # the derived proposal suffixes until free, and an explicit
        # existing branch is a hard block (no duplicate).
        work = make_repo(self.base, remotes={"origin": GITHUB_URL})
        (work / "file.txt").write_text("changed\n", encoding="utf-8")
        git(work, "branch", "ship/file")
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "staged_empty")
        self.assertEqual(payload["topic"], "ship/file-2")
        rc2, payload2 = decide(work, "--branch", "ship/file")
        self.assertEqual(rc2, 1)
        self.assertEqual(payload2["reason"], "explicit_branch_exists")
        self.assertIsNone(payload2["topic"])

    def test_empty_staged_on_main_ambiguous_remote_blocks_proposal(self):
        work = make_repo(self.base, remotes={"origin": GITHUB_URL,
                                             "other": "https://github.com/example/other.git"})
        (work / "file.txt").write_text("changed\n", encoding="utf-8")
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "ambiguous_remote")
        self.assertIsNone(payload["remote"])

    def test_branch_before_staging_on_main_carries_edits_and_reruns(self):
        # End-to-end branch-before-add ordering: helper proposes,
        # Worker switches -c that proposal carrying edits, verifies
        # the carry, stages exact paths, and reruns to selected.
        work = make_repo(self.base, remotes={"origin": GITHUB_URL})
        (work / "file.txt").write_text("changed\n", encoding="utf-8")
        (work / "new.txt").write_text("payload\n", encoding="utf-8")
        before_head = git(work, "rev-parse", "HEAD")
        before_unstaged = sorted(
            line for line in git(work, "diff", "--name-only").splitlines() if line)
        before_untracked = sorted(
            line for line in git(work, "ls-files", "--others", "--exclude-standard").splitlines() if line)
        rc0, payload0 = decide(work)
        self.assertEqual(rc0, 1)
        self.assertEqual(payload0["reason"], "staged_empty")
        self.assertTrue(payload0["on_main"])
        proposal = payload0["topic"]
        self.assertTrue(proposal.startswith("ship/"))
        # Branch before any add: the index is still empty on main
        # and no staging has run while on main.
        self.assertEqual(git(work, "branch", "--show-current"), "main")
        self.assertEqual(git(work, "diff", "--cached", "--name-only"), "")
        git(work, "switch", "-c", proposal)
        # Carry verification: topic current + not main, HEAD same,
        # index still empty, unstaged/untracked sets unchanged.
        self.assertEqual(git(work, "branch", "--show-current"), proposal)
        self.assertNotEqual(git(work, "branch", "--show-current"), "main")
        self.assertEqual(git(work, "rev-parse", "HEAD"), before_head)
        self.assertEqual(git(work, "diff", "--cached", "--name-only"), "")
        self.assertEqual(sorted(
            line for line in git(work, "diff", "--name-only").splitlines() if line),
            before_unstaged)
        self.assertEqual(sorted(
            line for line in git(work, "ls-files", "--others", "--exclude-standard").splitlines() if line),
            before_untracked)
        # Exact-path staging only now that the topic is checked out.
        for path in ("file.txt", "new.txt"):
            git(work, "add", "--", path)
        rc, payload = decide(work)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["status"], "selected")
        self.assertEqual(payload["topic"], proposal)
        self.assertEqual(payload["ref"], f"refs/heads/{proposal}")
        self.assertFalse(payload["on_main"])
        self.assertEqual(sorted(payload["staged_files"]), ["file.txt", "new.txt"])

    def test_clean_empty_on_main_is_scope_blocker(self):
        work = make_repo(self.base, remotes={"origin": GITHUB_URL})
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "staged_empty")
        self.assertTrue(payload["on_main"])
        self.assertEqual(payload["scope"]["unstaged"], [])
        self.assertEqual(payload["scope"]["untracked"], [])
        # No work to ship: no branch proposal.
        self.assertIsNone(payload["topic"])

    def test_nonempty_index_on_main_preserved_and_scope_unclean(self):
        # A pre-existing non-empty index is preserved, never broadened:
        # unstaged or untracked alongside it is scope_unclean rather
        # than staged_empty, so no auto-staging applies.
        work = make_repo(self.base, remotes={"origin": GITHUB_URL})
        stage(work, "file.txt")
        (work / "untracked.txt").write_text("payload\n", encoding="utf-8")
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "scope_unclean")
        self.assertFalse(payload["scope"]["staged_empty"])

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

    def test_candidate_resume_selects_exact_head(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        candidate = commit_candidate(work)
        rc, payload = decide(work, "--candidate", candidate)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["status"], "selected")
        self.assertEqual(payload["candidate"], candidate)
        self.assertEqual(payload["topic"], "feat/topic")
        self.assertEqual(payload["ref"], "refs/heads/feat/topic")
        self.assertEqual(payload["remote"], "origin")
        self.assertTrue(payload["selection"].startswith("candidate_resume/"))
        self.assertIsNone(payload["suggested_message"])

    def test_candidate_plain_invocation_stays_staged_empty(self):
        # A committed candidate with an empty index must never be
        # selected for pushing by a plain (non-resume) invocation.
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        commit_candidate(work)
        rc, payload = decide(work)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "staged_empty")
        self.assertIsNone(payload["candidate"])

    def test_candidate_wrong_head_blocks(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        commit_candidate(work)
        parent = git(work, "rev-parse", "HEAD^")
        rc, payload = decide(work, "--candidate", parent)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "candidate_not_head")

    def test_candidate_unknown_blocks(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        commit_candidate(work)
        rc, payload = decide(work, "--candidate", "f" * 40)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "candidate_unknown")

    def test_candidate_invalid_format_blocks(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        commit_candidate(work)
        rc, payload = decide(work, "--candidate", "deadbeef")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "candidate_invalid")

    def test_candidate_dirty_blocks(self):
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        candidate = commit_candidate(work)
        (work / "untracked.txt").write_text("payload\n", encoding="utf-8")
        rc, payload = decide(work, "--candidate", candidate)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "candidate_dirty")

    def test_candidate_on_main_blocks(self):
        work = make_repo(self.base, remotes={"origin": GITHUB_URL})
        main_sha = git(work, "rev-parse", "HEAD")
        rc, payload = decide(work, "--candidate", main_sha)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "candidate_on_main")

    def test_candidate_already_in_main_blocks(self):
        # Topic pointing at the main tip with no new commit has
        # nothing to resume.
        work = make_repo(self.base, branch="feat/topic",
                         remotes={"origin": GITHUB_URL})
        main_sha = git(work, "rev-parse", "refs/heads/main")
        rc, payload = decide(work, "--candidate", main_sha)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["reason"], "candidate_not_ahead")

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
