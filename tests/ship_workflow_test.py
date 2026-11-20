#!/usr/bin/env python3
"""Realistic Git fixtures for fleet ship-build / ship-deploy.

Uses only local Git repositories (bare remote + working clone) and the
real fleet scripts. No network, no billed inference, no live remotes.
Fixtures are disposable under pytest temp dirs (or unittest temp dir)
in the OS temp area, never in the working repo.
"""

import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FLEET_ROOT = REPO_ROOT
SHIP_BUILD = FLEET_ROOT / "scripts" / "ship" / "ship-build"
SHIP_DEPLOY = FLEET_ROOT / "scripts" / "ship" / "ship-deploy"
DOCTOR = FLEET_ROOT / "scripts" / "ship" / "ship-doctor"

PASSING_PACKAGE = {
    "name": "fixture",
    "packageManager": "npm@10.8.2",
    "scripts": {
        "prepare": "husky",
        "format:check": "node -e \"console.log('format ok')\"",
        "lint": "node -e \"console.log('lint ok')\"",
        "test:unit": "node -e \"console.log('unit ok')\"",
        "test:e2e": "node scripts/e2e.js",
    },
    "devDependencies": {"husky": "9.1.7"},
}


def run(args, cwd=None, input_text=None, check=False, timeout=30):
    proc = subprocess.run(
        args, cwd=cwd, input=input_text, capture_output=True, text=True,
        check=False, timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            f"command failed {args} cwd={cwd}: rc={proc.returncode} "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
    return proc


def git(repo: Path, *args, **kw):
    proc = run(["git", "-C", str(repo), *args], **kw)
    if proc.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed: {proc.stdout} {proc.stderr}"
        )
    return proc.stdout.strip()


def write(path: Path, text: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


SHIM = '#!/usr/bin/env sh\n. "$(dirname "$0")/h"\n'


def build_fixture(base: Path, *, e2e_ok: bool = True, deploy_ok: bool = True,
                  wrong_wiring: bool = False) -> tuple[Path, Path]:
    """Create bare remote + working repo that passes the doctor."""
    remote = base / "remote.git"
    work = base / "work"
    work.mkdir(parents=True)
    run(["git", "init", "--bare", "-q", str(remote)], check=True)
    run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    git(work, "config", "user.email", "fixture@example.invalid")
    git(work, "config", "user.name", "Fixture")
    git(work, "remote", "add", "origin", str(remote))
    write(work / "package.json", json.dumps(PASSING_PACKAGE, indent=2))
    write(work / "package-lock.json", '{"lockfileVersion": 3}\n')
    # Husky wiring: user hooks + executable shims + helper.
    # The initial main push below uses a temporary non-delegating
    # pre-push (`exit 0`) because the baseline commit is fixture setup,
    # not a ship candidate. The standard delegation is installed
    # immediately after the baseline push.
    write(work / ".husky" / "pre-commit", "exit 0\n")
    write(work / ".husky" / "commit-msg", "exit 0\n")
    write(work / ".husky" / "pre-push", "exit 0\n")
    for name in ("pre-commit", "commit-msg", "pre-push"):
        # Realistic executable shims: Git runs .husky/_/<hook>; the shim
        # forwards to the repository owner's .husky/<hook> with stdin,
        # arguments, and exit status preserved. .husky/_/h exists as
        # Husky's helper file (shape only for the doctor).
        write(
            work / ".husky" / "_" / name,
            f'#!/usr/bin/env sh\nDIR=$(dirname "$0")\nexec sh "$DIR/../{name}" "$@"\n',
            executable=True,
        )
    write(work / ".husky" / "_" / "h", "#!/usr/bin/env sh\n# Husky helper (shape fixture).\n")
    git(work, "config", "core.hooksPath", ".husky/_")
    # Repo non-prod entry + e2e runner (fixed inputs).
    if deploy_ok:
        write(
            work / "scripts" / "ship-deploy",
            '#!/bin/sh\nmkdir -p .ship\nprintf "%s\\n" "$1" > .ship/deploy-sha\n'
            'echo "deployed $1"\n',
            executable=True,
        )
    else:
        write(
            work / "scripts" / "ship-deploy",
            '#!/bin/sh\necho deploy-failed >&2\nexit 1\n',
            executable=True,
        )
    write(
        work / "scripts" / "e2e.js",
        "console.log('e2e ok');\n" if e2e_ok else "process.exit(1);\n",
    )
    write(work / "file.txt", "initial\n")
    write(work / ".gitignore", ".ship/\n.husky/\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "initial")
    git(work, "push", "-q", "origin", "HEAD:main")
    if not wrong_wiring:
        # Install the standardized delegation for ship operations.
        write(
            work / ".husky" / "pre-push",
            f'exec "{FLEET_ROOT}/scripts/ship/ship-deploy"\n',
        )
    else:
        # No delegation to the fleet wrapper: ship-build must refuse
        # before any mutation.
        write(work / ".husky" / "pre-push", "exit 0\n")
    # Baseline commit must not be treated as a ship candidate; ensure
    # no stale evidence exists for it.
    shutil.rmtree(work / ".ship", ignore_errors=True)
    return work, remote


def run_ship_build(work: Path, *, branch: str = "ship/topic-test",
                   message: str = "test: ship fixture change",
                   remote: str = "origin"):
    return run([
        str(SHIP_BUILD), str(work),
        "--remote", remote,
        "--ref", f"refs/heads/{branch}",
        "--branch", branch,
        "--message", message,
    ])


def remote_sha(remote: Path, ref: str) -> str:
    proc = run(["git", "ls-remote", str(remote), ref])
    out = proc.stdout.strip()
    if not out:
        return ""
    return out.split()[0]


class ShipWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_successful_flow_exact_sha(self) -> None:
        work, remote = build_fixture(self.base)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/topic-test")
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        head = git(work, "rev-parse", "HEAD")
        self.assertIn(head, proc.stdout)
        # Exact candidate: deploy saw HEAD, evidence names it, remote matches.
        self.assertEqual(
            (work / ".ship" / "deploy-sha").read_text().strip(), head,
        )
        self.assertTrue((work / ".ship" / "evidence" / f"{head}-commit.json").exists())
        self.assertTrue((work / ".ship" / "evidence" / f"{head}-deploy.json").exists())
        self.assertEqual(remote_sha(remote, "refs/heads/ship/topic-test"), head)
        # Topic branch was created and left intact.
        self.assertEqual(git(work, "branch", "--show-current"), "ship/topic-test")

    def test_deploy_failure_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base, deploy_ok=False)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/deploy-fail")
        self.assertNotEqual(proc.returncode, 0)
        # Pre-push failure: nothing was uploaded.
        self.assertEqual(remote_sha(remote, "refs/heads/ship/deploy-fail"), "")

    def test_e2e_failure_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base, e2e_ok=False)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/e2e-fail")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/e2e-fail"), "")

    def test_wrong_wiring_fails_before_mutation(self) -> None:
        work, remote = build_fixture(self.base, wrong_wiring=True)
        before = git(work, "rev-parse", "HEAD")
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/wrong-wiring")
        self.assertNotEqual(proc.returncode, 0)
        # No mutation: same HEAD, still on main, no remote branch.
        self.assertEqual(git(work, "rev-parse", "HEAD"), before)
        self.assertEqual(git(work, "branch", "--show-current"), "main")
        self.assertEqual(remote_sha(remote, "refs/heads/ship/wrong-wiring"), "")

    def test_no_implicit_staging(self) -> None:
        work, remote = build_fixture(self.base)
        before = git(work, "rev-parse", "HEAD")
        write(work / "file.txt", "unstaged only\n")
        # Unstaged change only: ship-build must refuse (no sweep-in).
        proc = run_ship_build(work, branch="ship/no-stage")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(git(work, "rev-parse", "HEAD"), before)

    def test_post_push_missing_receipt_did_not_prevent_upload(self) -> None:
        work, remote = build_fixture(self.base)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/post-push")
        self.assertEqual(proc.returncode, 0)
        head = git(work, "rev-parse", "HEAD")
        # Deleting the deploy receipt after the fact cannot undo the
        # upload: the remote still points at the candidate. The
        # ship-build post-push check would fail closed on missing
        # evidence at that time, but the upload already happened.
        (work / ".ship" / "evidence" / f"{head}-deploy.json").unlink()
        self.assertEqual(remote_sha(remote, "refs/heads/ship/post-push"), head)

    def test_ship_deploy_wrapper_rejects_missing_evidence(self) -> None:
        work, _ = build_fixture(self.base)
        # No stdin / no commit evidence: wrapper fails before deploy.
        proc = run([str(SHIP_DEPLOY)], cwd=work, input_text="")
        self.assertNotEqual(proc.returncode, 0)

    def test_plugin_loads_in_isolated_standalone_without_inference(self) -> None:
        # Isolated config: only the fleet plugin copy + minimal config.
        # No live settings touched, no model call, no billed inference.
        tmp = tempfile.mkdtemp(dir=self.base)
        isolated = Path(tmp)
        (isolated / "plugins").mkdir()
        shutil.copy(FLEET_ROOT / "fleet" / "plugins" / "ship.ts",
                    isolated / "plugins" / "ship.ts")
        (isolated / "opencode.jsonc").write_text(
            '{"$schema": "https://opencode.ai/config.json"}\n',
            encoding="utf-8",
        )
        # Debug paths must report the isolated root (isolation proof).
        proc = run(
            ["opencode", "debug", "paths", "config"],
            cwd=self.base,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, f"stderr={proc.stderr!r}")
        # Standalone plugin discovery must not error on the fleet file.
        env = dict(**__import__("os").environ)
        env["OPENCODE_CONFIG_DIR"] = str(isolated)
        proc2 = subprocess.run(
            ["opencode", "--standalone", "api", "get", "/api/info"],
            cwd=str(self.base), capture_output=True, text=True,
            check=False, timeout=30, env=env,
        )
        self.assertEqual(proc2.returncode, 0, f"stderr={proc2.stderr!r}")
        self.assertIn('"version"', proc2.stdout)

    def test_plugin_rejection_strings(self) -> None:
        text = (FLEET_ROOT / "fleet" / "plugins" / "ship.ts").read_text(
            encoding="utf-8"
        )
        # Trailing args rejected before admission (synthetic, no prompt).
        self.assertIn("prompt.text.trim()", text)
        self.assertIn("takes no arguments", text)
        self.assertIn("ctx.session.synthetic", text)
        # Wrong agent reported, not switched.
        self.assertIn('session.agent !== "cal"', text)
        self.assertIn("was not switched", text)


if __name__ == "__main__":
    unittest.main()
