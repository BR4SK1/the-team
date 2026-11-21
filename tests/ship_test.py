#!/usr/bin/env python3
"""End-to-end Git + Husky v9 fixture tests for scripts/ship/ship and ship-deploy."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

FLEET_ROOT = Path(__file__).resolve().parent.parent
SHIP = FLEET_ROOT / "scripts" / "ship" / "ship"
DEPLOY_WRAPPER = FLEET_ROOT / "scripts" / "ship" / "ship-deploy"

SHIM = '#!/usr/bin/env sh\n. "$(dirname "$0")/h"\n'
HUSKY_HELPER = (
    "#!/usr/bin/env sh\n"
    'if [ "${HUSKY:-}" = "0" ]; then exit 0; fi\n'
    'hook="$(basename "$0")"\n'
    'dir="$(dirname "$0")/.."\n'
    'exec sh -e "$dir/$hook" "$@"\n'
)


def write_text(path: Path, text: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.stdout.strip()


def parse_ship_result(stdout: str) -> dict:
    for line in stdout.splitlines():
        if line.startswith("SHIP_RESULT_JSON="):
            return json.loads(line.split("=", 1)[1])
    raise AssertionError(f"SHIP_RESULT_JSON not found in stdout:\n{stdout}")


class ShipWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

        self.bare = self.tmp / "remote.git"
        self.repo = self.tmp / "work"
        self.bin_dir = self.tmp / "bin"
        self.trace = self.tmp / "trace.log"
        self.bin_dir.mkdir()

        # Fake pnpm that records test:e2e env vars and active node version.
        write_text(
            self.bin_dir / "pnpm",
            f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "run" && "$2" == "test:e2e" ]]; then
  printf 'e2e target=%s deployed=%s node=%s\\n' \\
    "${{SHIP_TARGET_SHA:-}}" "${{SHIP_DEPLOYED_SHA:-}}" "$(node --version 2>/dev/null || echo none)" \\
    >> "{self.trace}"
  if [[ -f "{self.tmp}/fail-e2e" ]]; then
    echo "simulated e2e failure" >&2
    exit 1
  fi
  exit 0
fi
exit 0
""",
            executable=True,
        )

        # Initialize bare remote + working repo wired via Git insteadOf.
        subprocess.run(
            ["git", "init", "--bare", "-b", "main", str(self.bare)],
            check=True,
            capture_output=True,
        )
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "core.hooksPath", ".husky/_")
        git(
            self.repo,
            "remote",
            "add",
            "origin",
            "https://github.com/example/fixture.git",
        )
        git(
            self.repo,
            "config",
            f"url.{self.bare}.insteadOf",
            "https://github.com/example/fixture.git",
        )

        pkg = {
            "name": "fixture",
            "packageManager": "pnpm@10.18.1",
            "scripts": {
                "prepare": "husky",
                "format:check": "true",
                "lint": "true",
                "test:unit": "true",
                "test:e2e": "true",
            },
            "devDependencies": {"husky": "9.1.7"},
        }
        write_text(self.repo / "package.json", json.dumps(pkg, indent=2) + "\n")
        write_text(self.repo / "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
        write_text(self.repo / ".gitignore", "ignored.tmp\n")
        write_text(self.repo / "README.md", "initial\n")

        write_text(
            self.repo / ".husky" / "pre-commit",
            f'printf "pre-commit\\n" >> "{self.trace}"\n'
            f'if [ -f "{self.tmp}/fail-pre-commit" ]; then exit 1; fi\n',
        )
        write_text(
            self.repo / ".husky" / "commit-msg",
            f'printf "commit-msg\\n" >> "{self.trace}"\n'
            f'if [ -f "{self.tmp}/fail-commit-msg" ]; then exit 1; fi\n',
        )
        write_text(
            self.repo / ".husky" / "pre-push",
            f'#!/bin/sh\nexec "{DEPLOY_WRAPPER}"\n',
        )
        for hook in ("pre-commit", "commit-msg", "pre-push"):
            write_text(self.repo / ".husky" / "_" / hook, SHIM, executable=True)
        write_text(self.repo / ".husky" / "_" / "h", HUSKY_HELPER)

        write_text(
            self.repo / "scripts" / "ship-deploy",
            f"""#!/usr/bin/env bash
set -euo pipefail
printf 'deploy sha=%s node=%s\\n' "$1" "$(node --version 2>/dev/null || echo none)" >> "{self.trace}"
if [[ -f "{self.tmp}/fail-deploy" ]]; then
  echo "simulated deploy failure" >&2
  exit 1
fi
if [[ -f "{self.tmp}/bad-deploy-sha" ]]; then
  echo "SHIP_DEPLOYED_SHA=0000000000000000000000000000000000000000"
  exit 0
fi
printf 'SHIP_DEPLOYED_SHA=%s\\n' "$1"
""",
            executable=True,
        )

        git(self.repo, "add", ".")
        git(self.repo, "commit", "--no-verify", "-m", "chore: initial fixture")
        git(self.repo, "push", "--no-verify", "-u", "origin", "main")

    def run_ship(
        self, *args: str, env_extra: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.bin_dir}:{env.get('PATH', '')}"
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [str(SHIP), str(self.repo), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def test_happy_path_from_main_branches_commits_deploys_pushes_and_returns_to_main(
        self,
    ) -> None:
        main_before = git(self.repo, "rev-parse", "refs/heads/main")
        write_text(self.repo / "hello.txt", "world\n")

        proc = self.run_ship(
            "--branch",
            "feat/hello",
            "--message",
            "feat: add hello file",
            "--stage",
            "hello.txt",
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout)
        result = parse_ship_result(proc.stdout)

        self.assertEqual(result["status"], "pushed")
        self.assertEqual(result["owner"], "example")
        self.assertEqual(result["name"], "fixture")
        self.assertEqual(result["branch"], "feat/hello")
        self.assertEqual(result["base"], "main")

        # Local main stayed untouched and checked out cleanly.
        self.assertEqual(git(self.repo, "branch", "--show-current"), "main")
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/main"), main_before)

        # Remote topic branch points to the exact candidate SHA.
        remote_sha = git(self.bare, "rev-parse", "refs/heads/feat/hello")
        self.assertEqual(remote_sha, result["sha"])

        # Hooks, deploy, and E2E ran in order with matching SHAs.
        trace_lines = self.trace.read_text(encoding="utf-8").splitlines()
        self.assertEqual(trace_lines[0], "pre-commit")
        self.assertEqual(trace_lines[1], "commit-msg")
        self.assertTrue(trace_lines[2].startswith(f"deploy sha={remote_sha}"))
        self.assertTrue(
            trace_lines[3].startswith(f"e2e target={remote_sha} deployed={remote_sha}")
        )

    def test_retry_clean_topic_branch_after_deploy_failure(self) -> None:
        write_text(self.repo / "feature.txt", "v1\n")
        write_text(self.tmp / "fail-e2e", "1\n")

        first = self.run_ship(
            "--branch",
            "feat/retry",
            "--message",
            "feat: add feature",
            "--stage",
            "feature.txt",
        )
        self.assertNotEqual(first.returncode, 0)
        # Commit succeeded on topic branch, but push was blocked by E2E failure.
        self.assertEqual(git(self.repo, "branch", "--show-current"), "feat/retry")
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        ls_remote = git(self.repo, "ls-remote", "origin", "refs/heads/feat/retry")
        self.assertEqual(ls_remote, "")

        # Now E2E passes; re-running ship with no --stage/--message pushes HEAD.
        (self.tmp / "fail-e2e").unlink()
        second = self.run_ship()
        self.assertEqual(second.returncode, 0, msg=second.stderr + second.stdout)
        result = parse_ship_result(second.stdout)
        self.assertEqual(result["branch"], "feat/retry")
        self.assertEqual(git(self.bare, "rev-parse", "refs/heads/feat/retry"), result["sha"])
        self.assertEqual(git(self.repo, "branch", "--show-current"), "main")

    def test_behind_only_main_fast_forwards_and_detects_conflict(self) -> None:
        # Advance origin/main from a separate clone.
        other = self.tmp / "other"
        subprocess.run(
            ["git", "clone", str(self.bare), str(other)],
            check=True,
            capture_output=True,
        )
        git(other, "config", "user.name", "Other")
        git(other, "config", "user.email", "other@example.invalid")
        write_text(other / "upstream.txt", "from upstream\n")
        git(other, "add", "upstream.txt")
        git(other, "commit", "-m", "chore: upstream change")
        git(other, "push", "origin", "main")
        upstream_sha = git(other, "rev-parse", "HEAD")

        # Conflicting local edit to the same file must fail cleanly.
        write_text(self.repo / "upstream.txt", "local conflict\n")
        conflict = self.run_ship(
            "--branch",
            "feat/conflict",
            "--message",
            "feat: touch upstream",
            "--stage",
            "upstream.txt",
        )
        self.assertNotEqual(conflict.returncode, 0)
        self.assertIn("conflict", conflict.stderr)
        (self.repo / "upstream.txt").unlink()

        # Non-conflicting local edit fast-forwards main and ships.
        write_text(self.repo / "local.txt", "ok\n")
        ok = self.run_ship(
            "--branch",
            "feat/ff",
            "--message",
            "feat: non-conflicting change",
            "--stage",
            "local.txt",
        )
        self.assertEqual(ok.returncode, 0, msg=ok.stderr + ok.stdout)
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/main"), upstream_sha)

    def test_local_main_ahead_blocks(self) -> None:
        write_text(self.repo / "ahead.txt", "unpushed\n")
        git(self.repo, "add", "ahead.txt")
        git(self.repo, "commit", "--no-verify", "-m", "chore: local main commit")
        write_text(self.repo / "next.txt", "more\n")

        proc = self.run_ship(
            "--branch",
            "feat/blocked",
            "--message",
            "feat: should block",
            "--stage",
            "next.txt",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("ahead", proc.stderr)

    def test_guards_and_deploy_validation(self) -> None:
        write_text(self.repo / "a.txt", "a\n")

        # HUSKY=0 rejected.
        p = self.run_ship(
            "--branch", "feat/h0", "--message", "feat: h0", "--stage", "a.txt",
            env_extra={"HUSKY": "0"},
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("HUSKY=0", p.stderr)

        # ship: prefix rejected before branching.
        p = self.run_ship(
            "--branch", "feat/prefix", "--message", "ship: bad", "--stage", "a.txt"
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(git(self.repo, "branch", "--show-current"), "main")

        # Gitignored path rejected before branching.
        write_text(self.repo / "ignored.tmp", "secret\n")
        p = self.run_ship(
            "--branch", "feat/ign", "--message", "feat: ign", "--stage", "ignored.tmp"
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("gitignored", p.stderr)
        (self.repo / "ignored.tmp").unlink()

        # Leftover untracked file rejected.
        write_text(self.repo / "stray.txt", "stray\n")
        p = self.run_ship(
            "--branch", "feat/stray", "--message", "feat: stray", "--stage", "a.txt"
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("working tree is not clean", p.stderr)
        # Clean up branch created for stray test and return to main.
        git(self.repo, "reset", "HEAD", "--", "a.txt")
        git(self.repo, "switch", "main")
        git(self.repo, "branch", "-D", "feat/stray")
        (self.repo / "stray.txt").unlink()

        # Wrong SHIP_DEPLOYED_SHA blocks push.
        write_text(self.tmp / "bad-deploy-sha", "1\n")
        p = self.run_ship(
            "--branch", "feat/badsha", "--message", "feat: badsha", "--stage", "a.txt"
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(
            git(self.repo, "ls-remote", "origin", "refs/heads/feat/badsha"), ""
        )

    def test_nvmrc_activates_pinned_node_version(self) -> None:
        fake_nvm = self.tmp / "nvm"
        fake_node = fake_nvm / "versions" / "node" / "v99.88.77" / "bin" / "node"
        write_text(fake_node, "#!/bin/sh\necho v99.88.77\n", executable=True)

        write_text(self.repo / ".nvmrc", "99.88.77\n")
        proc = self.run_ship(
            "--branch",
            "feat/nvmrc",
            "--message",
            "chore: pin node version",
            "--stage",
            ".nvmrc",
            env_extra={"NVM_DIR": str(fake_nvm)},
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout)
        trace = self.trace.read_text(encoding="utf-8")
        self.assertIn("node=v99.88.77", trace)


if __name__ == "__main__":
    unittest.main()
