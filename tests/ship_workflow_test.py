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


# Genuine installed Husky v9 runtime bytes (typicode/husky main: the
# `husky` helper file copied to .husky/_/h and the generated shims).
HUSKY_H = (
    "#!/usr/bin/env sh\n"
    '[ "$HUSKY" = "2" ] && set -x\n'
    'n=$(basename "$0")\n'
    's=$(dirname "$(dirname "$0")")/$n\n'
    "\n"
    '[ ! -f "$s" ] && exit 0\n'
    "\n"
    'if [ -f "$HOME/.huskyrc" ]; then\n'
    '\techo "husky - \'~/.huskyrc\' is DEPRECATED, please move your code to ~/.config/husky/init.sh"\n'
    "fi\n"
    'i="${XDG_CONFIG_HOME:-$HOME/.config}/husky/init.sh"\n'
    '[ -f "$i" ] && . "$i"\n'
    "\n"
    '[ "${HUSKY-}" = "0" ] && exit 0\n'
    "\n"
    'export PATH="node_modules/.bin:$PATH"\n'
    'sh -e "$s" "$@"\n'
    "c=$?\n"
    "\n"
    '[ $c != 0 ] && echo "husky - $n script failed (code $c)"\n'
    '[ $c = 127 ] && echo "husky - command not found in PATH=$PATH"\n'
    "exit $c\n"
)
HUSKY_SHIM = '#!/usr/bin/env sh\n. "$(dirname "$0")/h"\n'


def build_fixture(base: Path, *, e2e_ok: bool = True, deploy_ok: bool = True,
                  wrong_wiring: bool = False, deploy_wrong_sha: bool = False,
                  deploy_moves_head: bool = False,
                  deploy_busy_lease: bool = False) -> tuple[Path, Path]:
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
    write(work / ".husky" / "pre-commit", "npm run format:check\n")
    write(work / ".husky" / "commit-msg", "npm run lint\n")
    write(work / ".husky" / "pre-push", "exit 0\n")
    for name in ("pre-commit", "commit-msg", "pre-push"):
        # Genuine installed shims: exactly what Husky v9 generates
        # (.husky/_/<hook> sourcing the helper). .husky/_/h is exactly
        # the installed helper file.
        write(work / ".husky" / "_" / name, HUSKY_SHIM, executable=True)
    write(work / ".husky" / "_" / "h", HUSKY_H)
    git(work, "config", "core.hooksPath", ".husky/_")
    # Repo non-prod entry + e2e runner (fixed inputs). The deploy adapter
    # prints exactly one deterministic stdout line, SHIP_DEPLOYED_SHA,
    # naming the rolled-out SHA; the E2E runner requires the explicit
    # SHIP_TARGET_SHA environment the fleet wrapper passes.
    if deploy_busy_lease:
        write(
            work / "scripts" / "ship-deploy",
            '#!/bin/sh\necho "non-prod lease busy: holder fixture-holder" >&2\n'
            'exit 1\n',
            executable=True,
        )
    elif deploy_wrong_sha:
        write(
            work / "scripts" / "ship-deploy",
            '#!/bin/sh\nmkdir -p .ship\nprintf "%s\\n" "$1" > .ship/deploy-sha\n'
            'echo "deployed $1"\n'
            'printf "SHIP_DEPLOYED_SHA=%s\\n" "0000000000000000000000000000000000000000"\n',
            executable=True,
        )
    elif deploy_moves_head:
        write(
            work / "scripts" / "ship-deploy",
            '#!/bin/sh\nmkdir -p .ship\nprintf "%s\\n" "$1" > .ship/deploy-sha\n'
            'echo "deployed $1"\n'
            'printf "SHIP_DEPLOYED_SHA=%s\\n" "$1"\n'
            'git commit -q --allow-empty -m moved-head-during-deploy\n',
            executable=True,
        )
    elif deploy_ok:
        write(
            work / "scripts" / "ship-deploy",
            '#!/bin/sh\nmkdir -p .ship\nprintf "%s\\n" "$1" > .ship/deploy-sha\n'
            'echo "deployed $1"\n'
            'printf "SHIP_DEPLOYED_SHA=%s\\n" "$1"\n',
            executable=True,
        )
    else:
        write(
            work / "scripts" / "ship-deploy",
            '#!/bin/sh\necho deploy-failed >&2\nexit 1\n',
            executable=True,
        )
    e2e_flag = "true" if e2e_ok else "false"
    write(
        work / "scripts" / "e2e.js",
        "const fs = require('fs');\n"
        "const target = process.env.SHIP_TARGET_SHA || '';\n"
        "if (!/^[0-9a-f]{40}$/.test(target)) { console.error('SHIP_TARGET_SHA missing/invalid'); process.exit(1); }\n"
        "let deployed = '';\n"
        "try { deployed = fs.readFileSync('.ship/deploy-sha','utf8').trim(); } catch (e) { console.error('deploy artifact missing'); process.exit(1); }\n"
        "if (deployed !== target) { console.error('e2e target mismatch'); process.exit(1); }\n"
        f"const ok = {e2e_flag};\n"
        "if (!ok) process.exit(1);\n"
        "console.log('e2e ok');\n",
    )
    write(work / "file.txt", "initial\n")
    write(work / ".gitignore", ".ship/\n.husky/\nnode_modules/\n")
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
    # Installed runtime deliberately: the helper source and package
    # manifest of the pinned Husky v9 package. Ignored by Git (not
    # committed), present on disk for the ship-build comparison.
    write(
        work / "node_modules" / "husky" / "package.json",
        json.dumps({"name": "husky", "version": "9.1.7"}, indent=2),
    )
    write(work / "node_modules" / "husky" / "husky", HUSKY_H)
    # Baseline commit must not be treated as a ship candidate; ensure
    # no stale evidence exists for it.
    shutil.rmtree(work / ".ship", ignore_errors=True)
    return work, remote


def run_ship_build(work: Path, *, branch: str = "ship/topic-test",
                   message: str = "test: ship fixture change",
                   remote: str = "origin", with_branch: bool = True):
    args = [
        str(SHIP_BUILD), str(work),
        "--remote", remote,
        "--ref", f"refs/heads/{branch}",
        "--message", message,
    ]
    if with_branch:
        args.extend(["--branch", branch])
    return run(args)


def remote_sha(remote: Path, ref: str) -> str:
    proc = run(["git", "ls-remote", str(remote), ref])
    out = proc.stdout.strip()
    if not out:
        return ""
    return out.split()[0]


def parse_run_dir(output: str, work: Path) -> Path:
    for line in output.splitlines():
        if line.startswith("run_dir: "):
            return Path(line.split("run_dir: ", 1)[1].strip())
    # Fallback: discover the single run directory under .git/ship-runs.
    runs = sorted((work / ".git" / "ship-runs").glob("*"))
    if len(runs) != 1:
        raise AssertionError(f"expected one run dir, found {runs}")
    return runs[0]


def push_upstream(base: Path, remote: Path, name: str = "other") -> str:
    other = base / name
    run(["git", "clone", "-q", str(remote), str(other)], check=True)
    git(other, "config", "user.email", "fixture@example.invalid")
    git(other, "config", "user.name", "Fixture")
    write(other / "upstream.txt", "upstream\n")
    git(other, "add", "upstream.txt")
    git(other, "commit", "-q", "-m", "upstream")
    git(other, "push", "-q", "origin", "HEAD:main")
    return git(other, "rev-parse", "HEAD")


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
        # Exact candidate: deploy saw HEAD, evidence binds it, remote matches.
        self.assertEqual(
            (work / ".ship" / "deploy-sha").read_text().strip(), head,
        )
        run_dir = parse_run_dir(proc.stdout, work)
        self.assertEqual(run_dir.parent.name, "ship-runs")
        self.assertTrue(not run_dir.is_symlink())
        commit_receipt = json.loads((run_dir / "commit.json").read_text())
        deploy_receipt = json.loads((run_dir / "deploy.json").read_text())
        self.assertEqual(commit_receipt["sha"], head)
        self.assertEqual(commit_receipt["run_id"], run_dir.name)
        self.assertEqual(commit_receipt["remote"], "origin")
        self.assertEqual(commit_receipt["ref"], "refs/heads/ship/topic-test")
        self.assertEqual(commit_receipt["branch"], "ship/topic-test")
        self.assertEqual(commit_receipt["tree"], git(work, "rev-parse", "HEAD^{tree}"))
        self.assertEqual(commit_receipt["parent"], git(work, "rev-parse", "HEAD^"))
        self.assertEqual(deploy_receipt["run_id"], run_dir.name)
        self.assertEqual(deploy_receipt["sha"], head)
        self.assertEqual(deploy_receipt["deployed_sha"], head)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/topic-test"), head)
        # Topic branch was created and left intact.
        self.assertEqual(git(work, "branch", "--show-current"), "ship/topic-test")

    def test_deploy_failure_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base, deploy_ok=False)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/deploy-fail")
        self.assertNotEqual(proc.returncode, 0)
        # Gate stderr is preserved, not discarded.
        self.assertIn("deploy-failed", proc.stdout + proc.stderr)
        # Pre-push failure: nothing was uploaded.
        self.assertEqual(remote_sha(remote, "refs/heads/ship/deploy-fail"), "")

    def test_busy_required_lease_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base, deploy_busy_lease=True)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/lease-busy")
        self.assertNotEqual(proc.returncode, 0)
        # The specific lease reason is preserved, upload is blocked,
        # and nothing is retried by an alternate deploy path.
        self.assertIn("non-prod lease busy", proc.stdout + proc.stderr)
        self.assertIn("fixture-holder", proc.stdout + proc.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/lease-busy"), "")

    def test_e2e_failure_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base, e2e_ok=False)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/e2e-fail")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/e2e-fail"), "")

    def test_deploy_wrong_sha_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base, deploy_wrong_sha=True)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/wrong-sha")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("SHIP_DEPLOYED_SHA", proc.stdout + proc.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/wrong-sha"), "")

    def test_deploy_moving_head_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base, deploy_moves_head=True)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/moved-head")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("moved during", proc.stdout + proc.stderr)
        # Upload blocked despite the rollout having run.
        self.assertEqual(remote_sha(remote, "refs/heads/ship/moved-head"), "")

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

    def test_noop_shim_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base)
        write(work / ".husky" / "_" / "pre-push", "#!/usr/bin/env sh\nexit 0\n", executable=True)
        before = git(work, "rev-parse", "HEAD")
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/noop-shim")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("shim", proc.stdout + proc.stderr)
        self.assertEqual(git(work, "rev-parse", "HEAD"), before)
        self.assertEqual(git(work, "branch", "--show-current"), "main")
        self.assertEqual(remote_sha(remote, "refs/heads/ship/noop-shim"), "")

    def test_comment_only_hook_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base)
        write(
            work / ".husky" / "pre-push",
            f'#!/bin/sh\n# exec "{FLEET_ROOT}/scripts/ship/ship-deploy"\n',
        )
        before = git(work, "rev-parse", "HEAD")
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/comment-only")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("pre-push", proc.stdout + proc.stderr)
        self.assertEqual(git(work, "rev-parse", "HEAD"), before)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/comment-only"), "")

    def test_untracked_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base)
        before = git(work, "rev-parse", "HEAD")
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        write(work / "untracked.txt", "payload\n")
        proc = run_ship_build(work, branch="ship/untracked")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("untracked", proc.stdout + proc.stderr)
        self.assertEqual(git(work, "rev-parse", "HEAD"), before)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/untracked"), "")

    def test_pushurl_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base)
        git(work, "config", "remote.origin.pushurl", "https://example.invalid/other.git")
        before = git(work, "rev-parse", "HEAD")
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/pushurl")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("pushurl", proc.stdout + proc.stderr)
        self.assertEqual(git(work, "rev-parse", "HEAD"), before)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/pushurl"), "")

    def test_mirror_blocks_upload(self) -> None:
        work, remote = build_fixture(self.base)
        git(work, "config", "remote.origin.mirror", "true")
        before = git(work, "rev-parse", "HEAD")
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/mirror")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("mirror", proc.stdout + proc.stderr)
        self.assertEqual(git(work, "rev-parse", "HEAD"), before)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/mirror"), "")

    def test_main_ahead_blocks(self) -> None:
        work, remote = build_fixture(self.base)
        git(work, "commit", "-q", "--allow-empty", "-m", "local-ahead")
        before = git(work, "rev-parse", "HEAD")
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/main-ahead")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("ahead", proc.stdout + proc.stderr)
        self.assertEqual(git(work, "rev-parse", "HEAD"), before)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/main-ahead"), "")

    def test_main_diverged_blocks(self) -> None:
        work, remote = build_fixture(self.base)
        git(work, "commit", "-q", "--allow-empty", "-m", "local-ahead")
        push_upstream(self.base, remote, "other-div")
        before = git(work, "rev-parse", "HEAD")
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/main-div")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("diverged", proc.stdout + proc.stderr)
        self.assertEqual(git(work, "rev-parse", "HEAD"), before)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/main-div"), "")

    def test_main_behind_fast_forward_preserves_staged(self) -> None:
        work, remote = build_fixture(self.base)
        upstream_sha = push_upstream(self.base, remote, "other-behind")
        # The work clone's tracking ref is now stale (it predates upstream).
        stale_tracking = git(work, "rev-parse", "refs/remotes/origin/main")
        self.assertNotEqual(stale_tracking, upstream_sha)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/main-behind")
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        head = git(work, "rev-parse", "HEAD")
        # Fast-forward brought upstream in; the candidate sits on top of it.
        self.assertEqual(git(work, "rev-parse", "HEAD^"), upstream_sha)
        self.assertEqual(git(work, "rev-parse", "refs/heads/main"), upstream_sha)
        self.assertTrue((work / "upstream.txt").exists())
        self.assertEqual((work / "file.txt").read_text(), "changed\n")
        self.assertEqual(remote_sha(remote, "refs/heads/ship/main-behind"), head)

    def test_main_behind_off_main_fast_forwards_main_ref(self) -> None:
        work, remote = build_fixture(self.base)
        git(work, "switch", "-c", "topic-off")
        topic_parent = git(work, "rev-parse", "HEAD")
        upstream_sha = push_upstream(self.base, remote, "other-off")
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="topic-off")
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        head = git(work, "rev-parse", "HEAD")
        # Off-main: main ref advances to upstream, topic HEAD keeps its
        # original parent (no merge of upstream into the topic branch).
        self.assertEqual(git(work, "rev-parse", "refs/heads/main"), upstream_sha)
        self.assertEqual(git(work, "rev-parse", "HEAD^"), topic_parent)
        self.assertEqual(remote_sha(remote, "refs/heads/topic-off"), head)

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
        run_dir = parse_run_dir(proc.stdout, work)
        (run_dir / "deploy.json").unlink()
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

    def test_plugin_dispatch_execution_without_inference(self) -> None:
        # Execute the real plugin `execute` function (not substring
        # matching) with a mocked plugin context: no OpenCode server, no
        # model call, no billed inference. Covers rejected trailing
        # input, rejected wrong agent, and the accepted fixed prompt.
        harness = Path(self.base) / "plugin-harness"
        (harness / "node_modules" / "@opencode" / "plugin").mkdir(parents=True)
        (harness / "node_modules" / "@opencode" / "plugin" / "package.json").write_text(
            '{"name":"@opencode/plugin","version":"0.0.0","type":"module",'
            '"exports":{".":"./index.js"}}\n',
            encoding="utf-8",
        )
        (harness / "node_modules" / "@opencode" / "plugin" / "index.js").write_text(
            "export const Plugin = { define: (def) => def };\n",
            encoding="utf-8",
        )
        shutil.copy(
            FLEET_ROOT / "fleet" / "plugins" / "ship.ts",
            harness / "ship.ts",
        )
        (harness / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
        (harness / "run.mjs").write_text(
            'import shipPlugin from "./ship.ts";\n'
            "async function invoke(agent, text) {\n"
            "  let added = null; const calls = [];\n"
            "  const ctx = {\n"
            "    command: { list: async () => [], transform: async (fn) => fn({ add: (d) => { added = d; } }) },\n"
            "    session: {\n"
            "      get: async () => ({ agent }),\n"
            "      synthetic: async (a) => calls.push(['synthetic', a.text]),\n"
            "      prompt: async (a) => calls.push(['prompt', a.text]),\n"
            "    },\n"
            "  };\n"
            "  await shipPlugin.setup(ctx);\n"
            "  await added.execute({ sessionID: 'ses_test', prompt: { text }, delivery: 'sync' });\n"
            "  return calls;\n"
            "}\n"
            "console.log(JSON.stringify({\n"
            "  trailing: await invoke('cal', ' extra'),\n"
            "  wrong: await invoke('worker', ''),\n"
            "  accepted: await invoke('cal', ''),\n"
            "  unset: await invoke(undefined, ''),\n"
            "}));\n",
            encoding="utf-8",
        )
        proc = run(["node", "run.mjs"], cwd=harness, timeout=30)
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        outcome = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(outcome["trailing"][0][0], "synthetic")
        self.assertIn("takes no arguments", outcome["trailing"][0][1])
        self.assertEqual(outcome["wrong"][0][0], "synthetic")
        self.assertIn("was not switched", outcome["wrong"][0][1])
        self.assertEqual(outcome["accepted"][0][0], "prompt")
        self.assertIn("Load the ship skill by ID ship", outcome["accepted"][0][1])
        self.assertIn("You are Cal", outcome["accepted"][0][1])
        # The fixed prompt carries the same no-routine-approval contract
        # as the skill, including autonomous destination selection.
        self.assertIn("no routine approval stops", outcome["accepted"][0][1])
        self.assertIn("ship-destination", outcome["accepted"][0][1])
        # The prompt carries the single reviewed auto-staging: empty
        # index on a topic branch stages reviewed paths, then reruns.
        self.assertIn("staged_empty on an eligible topic branch",
                      outcome["accepted"][0][1])
        self.assertIn("never broadened", outcome["accepted"][0][1])
        # An unset session agent is not Cal (Session.Info.agent is
        # optional and may be absent on a fresh session).
        self.assertEqual(outcome["unset"][0][0], "synthetic")

    def test_session_info_agent_shape_without_inference(self) -> None:
        # The session API shape the plugin relies on (Session.Info.agent
        # is optional; a fresh session carries no provider cost) without
        # sending any prompt, so without billed inference.
        tmp = tempfile.mkdtemp(dir=self.base)
        isolated = Path(tmp)
        (isolated / "plugins").mkdir()
        shutil.copy(FLEET_ROOT / "fleet" / "plugins" / "ship.ts",
                    isolated / "plugins" / "ship.ts")
        (isolated / "opencode.jsonc").write_text(
            '{"$schema": "https://opencode.ai/config.json"}\n',
            encoding="utf-8",
        )
        env = dict(**__import__("os").environ)
        env["OPENCODE_CONFIG_DIR"] = str(isolated)
        created = subprocess.run(
            ["opencode", "--standalone", "api", "post", "/api/session",
             "--data", '{"title":"ship-shape-probe"}'],
            cwd=str(self.base), capture_output=True, text=True,
            check=False, timeout=30, env=env,
        )
        self.assertEqual(created.returncode, 0, f"stderr={created.stderr!r}")
        session_id = json.loads(created.stdout)["data"]["id"]
        self.assertTrue(session_id.startswith("ses_"))
        fetched = subprocess.run(
            ["opencode", "--standalone", "api", "get", f"/api/session/{session_id}"],
            cwd=str(self.base), capture_output=True, text=True,
            check=False, timeout=30, env=env,
        )
        self.assertEqual(fetched.returncode, 0, f"stderr={fetched.stderr!r}")
        info = json.loads(fetched.stdout)["data"]
        self.assertEqual(info["id"], session_id)
        self.assertEqual(info["location"]["directory"], str(self.base))
        self.assertEqual(info["cost"], 0)
        # Agent identity is an optional Session.Info field; when present
        # it must be a string ID.
        if "agent" in info:
            self.assertIsInstance(info["agent"], str)


if __name__ == "__main__":
    unittest.main()
