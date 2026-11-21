#!/usr/bin/env python3
"""Realistic Git fixtures for fleet ship-build / ship-deploy.

Uses only local Git repositories (bare remote + working clone) and the
real fleet scripts. No network, no billed inference, no live remotes.
Fixtures are disposable under pytest temp dirs (or unittest temp dir)
in the OS temp area, never in the working repo.
"""

import json
import os
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
SHIP_RESUME = FLEET_ROOT / "scripts" / "ship" / "ship-resume"
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


def run(args, cwd=None, input_text=None, check=False, timeout=30, env=None):
    proc = subprocess.run(
        args, cwd=cwd, input=input_text, capture_output=True, text=True,
        check=False, timeout=timeout, env=env,
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


ISOLATED_IMAGE = "node:26.13.1-alpine@sha256:" + "a" * 64
FAKE_IMAGE_ID = "sha256:" + "b" * 64


def build_fixture(base: Path, *, e2e_ok: bool = True, deploy_ok: bool = True,
                  wrong_wiring: bool = False, deploy_wrong_sha: bool = False,
                  deploy_moves_head: bool = False,
                  deploy_busy_lease: bool = False,
                  deploy_fail_marker: bool = False,
                  isolated: bool = False,
                  isolated_image: str | None = None) -> tuple[Path, Path]:
    """Create bare remote + working repo that passes the doctor.

    deploy_fail_marker: the non-prod deploy entry fails while the
    marker file .git/fixture-fail-deploy exists and succeeds when it
    is absent. The marker lives under .git, so toggling it never
    dirties the worktree; resume tests use it to stage a retained
    candidate after an initially failed pre-push gate.
    """
    fail_check = (
        'if [ -f .git/fixture-fail-deploy ]; then '
        'echo marker-deploy-failed >&2; exit 1; fi\n'
        if deploy_fail_marker else ""
    )
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
            '#!/bin/sh\n'
            + fail_check +
            'mkdir -p .ship\nprintf "%s\\n" "$1" > .ship/deploy-sha\n'
            'if [ -n "${FAKE_DOCKER_LOG:-}" ]; then printf "deploy\\n" >> "$FAKE_DOCKER_LOG"; fi\n'
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
    if isolated:
        # In the isolated workspace (a candidate-tree export) the
        # host deploy artifact is not present; the candidate is
        # carried by the explicit environment the runner passes.
        write(
            work / "scripts" / "e2e.js",
            "const target = process.env.SHIP_TARGET_SHA || '';\n"
            "const deployed = process.env.SHIP_DEPLOYED_SHA || '';\n"
            "if (!/^[0-9a-f]{40}$/.test(target)) { console.error('SHIP_TARGET_SHA missing/invalid'); process.exit(1); }\n"
            "if (deployed !== target) { console.error('e2e target mismatch'); process.exit(1); }\n"
            f"const ok = {e2e_flag};\n"
            "if (!ok) process.exit(1);\n"
            "console.log('e2e ok');\n",
        )
    else:
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
    if isolated:
        contract = {
            "schema_version": 1,
            "runner": {
                "kind": "oci",
                "image": isolated_image or ISOLATED_IMAGE,
                "command": ["npm", "run", "test:e2e"],
            },
        }
        write(
            work / ".ship" / "e2e-runner.json",
            json.dumps(contract, indent=2) + "\n",
        )
    write(work / "file.txt", "initial\n")
    if isolated:
        write(work / ".gitignore", ".ship/deploy-sha\n.husky/\nnode_modules/\n")
    else:
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
    # no stale evidence exists for it. The isolated contract file
    # itself is tracked and must stay on disk.
    deploy_sha = work / ".ship" / "deploy-sha"
    if deploy_sha.exists():
        deploy_sha.unlink()
    if not isolated:
        shutil.rmtree(work / ".ship", ignore_errors=True)
    return work, remote


FAKE_DOCKER_SOURCE = '''#!/usr/bin/env python3
import os
import sys

args = sys.argv[1:]
log = os.environ.get("FAKE_DOCKER_LOG", "")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("docker " + " ".join(args) + "\\n")
mode = os.environ.get("FAKE_DOCKER_MODE", "ok")
if args[:2] == ["image", "inspect"]:
    if mode == "missing-image":
        print("fake docker: image not found", file=sys.stderr)
        sys.exit(1)
    image_id = "b" * 64
    if mode == "image-changed":
        state = os.environ.get("FAKE_DOCKER_STATE", "")
        count = 0
        if state and os.path.exists(state):
            with open(state, encoding="utf-8") as handle:
                count = int(handle.read().strip() or "0")
        count += 1
        if state:
            with open(state, "w", encoding="utf-8") as handle:
                handle.write(str(count))
        if count > 1:
            image_id = "c" * 64
    print("sha256:" + image_id)
    sys.exit(0)
if args and args[0] == "run":
    # The command is the last three arguments; the image is the
    # argument before it. Verify the workspace mount exists.
    if len(args) < 4:
        print("fake docker: run missing command", file=sys.stderr)
        sys.exit(1)
    workspace = ""
    envs = {}
    index = 1
    while index < len(args):
        if args[index] == "--volume":
            workspace = args[index + 1].split(":", 1)[0]
            index += 2
        elif args[index] == "--env":
            key, _, value = args[index + 1].partition("=")
            envs[key] = value
            index += 2
        elif args[index].startswith("--env="):
            key, _, value = args[index][6:].partition("=")
            envs[key] = value
            index += 1
        elif args[index].startswith("-"):
            if args[index] in ("--tmpfs", "--pids-limit", "--user", "--workdir", "--network", "--cap-drop", "--security-opt", "--pull"):
                index += 2
            else:
                index += 1
        else:
            break
    if not workspace or not os.path.isdir(workspace):
        print("fake docker: workspace mount missing", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(os.path.join(workspace, "package.json")):
        print("fake docker: candidate package.json missing in workspace", file=sys.stderr)
        sys.exit(1)
    target = envs.get("SHIP_TARGET_SHA", "")
    if len(target) != 40 or envs.get("SHIP_DEPLOYED_SHA") != target:
        print("fake docker: SHIP_TARGET_SHA/SHIP_DEPLOYED_SHA mismatch", file=sys.stderr)
        sys.exit(1)
    if mode == "e2e-fail":
        print("e2e failed (fake docker)", file=sys.stderr)
        sys.exit(1)
    print("e2e ok (isolated fake docker)")
    sys.exit(0)
print("fake docker: unsupported invocation", file=sys.stderr)
sys.exit(1)
'''


def make_fake_docker(base: Path) -> Path:
    bin_dir = base / "fake-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    docker = bin_dir / "docker"
    write(docker, FAKE_DOCKER_SOURCE, executable=True)
    return bin_dir


def isolated_env(base: Path, *, mode: str = "ok") -> tuple[dict, Path]:
    bin_dir = make_fake_docker(base)
    log = base / "fake-docker.log"
    log.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["FAKE_DOCKER_LOG"] = str(log)
    env["FAKE_DOCKER_MODE"] = mode
    env["FAKE_DOCKER_STATE"] = str(base / "fake-docker-state")
    return env, log


def run_ship_build(work: Path, *, branch: str = "ship/topic-test",
                   message: str = "test: ship fixture change",
                   remote: str = "origin", with_branch: bool = True,
                   env=None):
    args = [
        str(SHIP_BUILD), str(work),
        "--remote", remote,
        "--ref", f"refs/heads/{branch}",
        "--message", message,
    ]
    if with_branch:
        args.extend(["--branch", branch])
    return run(args, env=env)


def run_ship_resume(work: Path, *, sha: str, branch: str,
                    remote: str = "origin", env=None):
    return run([
        str(SHIP_RESUME), str(work),
        "--remote", remote,
        "--ref", f"refs/heads/{branch}",
        "--sha", sha,
    ], env=env)


def set_fail_marker(work: Path) -> None:
    (work / ".git" / "fixture-fail-deploy").write_text("fail\n", encoding="utf-8")


def clear_fail_marker(work: Path) -> None:
    (work / ".git" / "fixture-fail-deploy").unlink(missing_ok=True)


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
        self.assertEqual(deploy_receipt["e2e_mode"], "legacy_host")
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

    # --- Explicit resume of a retained candidate ---

    def retained_candidate(self, *, branch: str, isolated: bool = False,
                           env=None) -> tuple[Path, Path, str, Path]:
        """Ship-build once with the deploy gate failing; the candidate
        commit and its commit receipt are retained locally, the
        destination branch is absent remotely."""
        work, remote = build_fixture(
            self.base, isolated=isolated, deploy_fail_marker=True
        )
        set_fail_marker(work)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch=branch, env=env)
        self.assertNotEqual(proc.returncode, 0,
                            f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        self.assertIn("marker-deploy-failed", proc.stdout + proc.stderr)
        candidate = git(work, "rev-parse", "HEAD")
        self.assertEqual(remote_sha(remote, f"refs/heads/{branch}"), "")
        self.assertEqual(git(work, "branch", "--show-current"), branch)
        run_dir = parse_run_dir(proc.stdout, work)
        self.assertFalse((run_dir / "deploy.json").exists())
        return work, remote, candidate, run_dir

    def test_resume_success_no_second_commit(self) -> None:
        work, remote, candidate, run_dir = self.retained_candidate(
            branch="ship/resume-ok"
        )
        parent = git(work, "rev-parse", "HEAD^")
        tree = git(work, "rev-parse", "HEAD^{tree}")
        receipt_before = json.loads((run_dir / "commit.json").read_text())
        clear_fail_marker(work)
        proc = run_ship_resume(work, sha=candidate, branch="ship/resume-ok")
        self.assertEqual(proc.returncode, 0,
                         f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        self.assertIn("resumed:", proc.stdout)
        # The same commit, same parent and tree: no second commit.
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)
        self.assertEqual(git(work, "rev-parse", "HEAD^"), parent)
        self.assertEqual(git(work, "rev-parse", "HEAD^{tree}"), tree)
        self.assertEqual(
            len([l for l in git(work, "log", "--oneline", "main..HEAD").splitlines() if l]),
            1,
        )
        self.assertEqual(remote_sha(remote, "refs/heads/ship/resume-ok"), candidate)
        self.assertEqual(
            (work / ".ship" / "deploy-sha").read_text().strip(), candidate,
        )
        # The immutable commit receipt is unchanged; deploy evidence
        # is fresh in the same run; the resume receipt is recorded.
        self.assertEqual(json.loads((run_dir / "commit.json").read_text()), receipt_before)
        deploy_receipt = json.loads((run_dir / "deploy.json").read_text())
        self.assertEqual(deploy_receipt["sha"], candidate)
        self.assertEqual(deploy_receipt["deployed_sha"], candidate)
        self.assertEqual(deploy_receipt["run_id"], run_dir.name)
        resume_receipt = json.loads((run_dir / "resume.json").read_text())
        self.assertEqual(resume_receipt["type"], "resume")
        self.assertEqual(resume_receipt["sha"], candidate)
        self.assertEqual(resume_receipt["run_id"], run_dir.name)

    def test_resume_gate_still_blocks(self) -> None:
        work, remote, candidate, run_dir = self.retained_candidate(
            branch="ship/resume-blocked"
        )
        # Marker still present: the resumed push's real pre-push gate
        # fails again and uploads nothing.
        proc = run_ship_resume(work, sha=candidate, branch="ship/resume-blocked")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("marker-deploy-failed", proc.stdout + proc.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/resume-blocked"), "")
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)
        self.assertFalse((run_dir / "deploy.json").exists())
        self.assertFalse((run_dir / "resume.json").exists())

    def test_automatic_recovery_from_derived_head(self) -> None:
        # No user-supplied SHA: the workflow derives the candidate
        # from HEAD (git rev-parse HEAD) and resumes exactly that
        # commit. The decision logic that produces the same value
        # automatically is covered in tests/ship_destination_test.py
        # (GitHub-URL fixtures, since the destination helper
        # verifies GitHub identity), while this fixture proves the
        # push path against a real local bare remote.
        work, remote, candidate, run_dir = self.retained_candidate(
            branch="ship/resume-auto"
        )
        parent = git(work, "rev-parse", "HEAD^")
        tree = git(work, "rev-parse", "HEAD^{tree}")
        clear_fail_marker(work)
        derived_sha = git(work, "rev-parse", "HEAD")
        self.assertEqual(derived_sha, candidate)
        proc = run_ship_resume(work, sha=derived_sha, branch="ship/resume-auto")
        self.assertEqual(proc.returncode, 0,
                         f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)
        self.assertEqual(git(work, "rev-parse", "HEAD^"), parent)
        self.assertEqual(git(work, "rev-parse", "HEAD^{tree}"), tree)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/resume-auto"), candidate)
        self.assertEqual(
            json.loads((run_dir / "deploy.json").read_text())["sha"], candidate
        )

    def test_ordinary_commit_without_receipt_not_auto_resumed(self) -> None:
        # An ordinary existing commit with no proven prior ship
        # receipt must never be auto-resumed or pushed.
        work, remote = build_fixture(self.base)
        candidate, run_dir = self.setup_candidate(work, branch="ship/topic-ordinary")
        shutil.rmtree(run_dir)
        derived_sha = git(work, "rev-parse", "HEAD")
        self.assertEqual(derived_sha, candidate)
        proc = run_ship_resume(work, sha=derived_sha, branch="ship/topic-ordinary")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("exactly one receipt", proc.stdout + proc.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/topic-ordinary"), "")
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)

    def test_resume_wrong_sha_blocks(self) -> None:
        work, remote, candidate, _run_dir = self.retained_candidate(
            branch="ship/resume-wrong-sha"
        )
        parent = git(work, "rev-parse", "HEAD^")
        clear_fail_marker(work)
        proc = run_ship_resume(work, sha=parent, branch="ship/resume-wrong-sha")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("does not equal the requested candidate", proc.stdout + proc.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/resume-wrong-sha"), "")
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)

    def test_resume_dirty_checkout_blocks(self) -> None:
        work, remote, candidate, _run_dir = self.retained_candidate(
            branch="ship/resume-dirty"
        )
        write(work / "untracked.txt", "payload\n")
        clear_fail_marker(work)
        proc = run_ship_resume(work, sha=candidate, branch="ship/resume-dirty")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("untracked", proc.stdout + proc.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/resume-dirty"), "")
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)
        # Resume never cleans the tree.
        self.assertTrue((work / "untracked.txt").exists())

    def test_resume_wrong_remote_and_branch_block(self) -> None:
        work, remote, candidate, _run_dir = self.retained_candidate(
            branch="ship/resume-target"
        )
        other_remote = self.base / "other-remote.git"
        run(["git", "init", "--bare", "-q", str(other_remote)], check=True)
        git(work, "remote", "add", "other", str(other_remote))
        clear_fail_marker(work)
        proc = run_ship_resume(
            work, sha=candidate, branch="ship/resume-target", remote="other"
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("prior commit evidence", proc.stdout + proc.stderr)
        self.assertEqual(remote_sha(other_remote, "refs/heads/ship/resume-target"), "")
        proc2 = run_ship_resume(work, sha=candidate, branch="ship/resume-other")
        self.assertNotEqual(proc2.returncode, 0)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/resume-other"), "")
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)

    def test_resume_ambiguous_evidence_blocks(self) -> None:
        work, remote, candidate, run_dir = self.retained_candidate(
            branch="ship/resume-ambiguous"
        )
        copy_dir = work / ".git" / "ship-runs" / "run-copy"
        shutil.copytree(run_dir, copy_dir)
        clear_fail_marker(work)
        proc = run_ship_resume(work, sha=candidate, branch="ship/resume-ambiguous")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("exactly one receipt", proc.stdout + proc.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/resume-ambiguous"), "")
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)

    def test_resume_without_prior_receipt_blocks(self) -> None:
        work, remote = build_fixture(self.base)
        candidate, run_dir = self.setup_candidate(work, branch="ship/topic-noreceipt")
        shutil.rmtree(run_dir)
        proc = run_ship_resume(work, sha=candidate, branch="ship/topic-noreceipt")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("exactly one receipt", proc.stdout + proc.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/topic-noreceipt"), "")
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)

    def test_resume_already_uploaded_blocks(self) -> None:
        work, remote = build_fixture(self.base)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/resume-uploaded")
        self.assertEqual(proc.returncode, 0,
                         f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        candidate = git(work, "rev-parse", "HEAD")
        proc2 = run_ship_resume(work, sha=candidate, branch="ship/resume-uploaded")
        self.assertNotEqual(proc2.returncode, 0)
        self.assertIn("already equals the candidate", proc2.stdout + proc2.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/resume-uploaded"), candidate)
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)

    def test_resume_already_rolled_out_blocks(self) -> None:
        work, remote = build_fixture(self.base)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        proc = run_ship_build(work, branch="ship/resume-rolled")
        self.assertEqual(proc.returncode, 0,
                         f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        candidate = git(work, "rev-parse", "HEAD")
        # The prior rollout succeeded (deploy evidence present) but
        # the uploaded ref is gone: resume must not duplicate the
        # rollout; the owner decides.
        run(["git", "-C", str(remote), "update-ref", "-d",
             "refs/heads/ship/resume-rolled"], check=True)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/resume-rolled"), "")
        proc2 = run_ship_resume(work, sha=candidate, branch="ship/resume-rolled")
        self.assertNotEqual(proc2.returncode, 0)
        self.assertIn("already succeeded", proc2.stdout + proc2.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/resume-rolled"), "")
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)

    def test_resume_advanced_remote_ref_blocks(self) -> None:
        work, remote, candidate, _run_dir = self.retained_candidate(
            branch="ship/resume-advanced"
        )
        # Push a competing commit onto the same topic branch from a
        # second clone, so the destination ref is already advanced.
        second = self.base / "second-clone-adv"
        run(["git", "clone", "-q", str(remote), str(second)], check=True)
        git(second, "config", "user.email", "fixture@example.invalid")
        git(second, "config", "user.name", "Fixture")
        git(second, "switch", "-c", "ship/resume-other-topic")
        write(second / "adv.txt", "competing\n")
        git(second, "add", "adv.txt")
        git(second, "commit", "-q", "-m", "competing")
        competing = git(second, "rev-parse", "HEAD")
        git(second, "push", "-q", "origin", "HEAD:refs/heads/ship/resume-advanced")
        self.assertEqual(
            remote_sha(remote, "refs/heads/ship/resume-advanced"), competing
        )
        clear_fail_marker(work)
        proc = run_ship_resume(work, sha=candidate, branch="ship/resume-advanced")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("already points elsewhere", proc.stdout + proc.stderr)
        # No overwrite: the remote ref still names the competing commit.
        self.assertEqual(
            remote_sha(remote, "refs/heads/ship/resume-advanced"), competing
        )
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)

    def test_resume_isolated_regenerates_preflight(self) -> None:
        env, log = isolated_env(self.base)
        work, remote, candidate, run_dir = self.retained_candidate(
            branch="ship/resume-isolated", isolated=True, env=env
        )
        # The failed attempt's read-only preflight was recorded.
        self.assertTrue((run_dir / "preflight.json").exists())
        clear_fail_marker(work)
        proc = run_ship_resume(
            work, sha=candidate, branch="ship/resume-isolated", env=env
        )
        self.assertEqual(proc.returncode, 0,
                         f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        self.assertIn("removed stale preflight evidence", proc.stdout)
        self.assertEqual(git(work, "rev-parse", "HEAD"), candidate)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/resume-isolated"), candidate)
        preflight_receipt = json.loads((run_dir / "preflight.json").read_text())
        deploy_receipt = json.loads((run_dir / "deploy.json").read_text())
        self.assertEqual(preflight_receipt["sha"], candidate)
        self.assertEqual(deploy_receipt["e2e_mode"], "isolated_oci")
        self.assertEqual(deploy_receipt["sha"], candidate)
        log_text = log.read_text(encoding="utf-8")
        # First attempt preflight (1 inspect), resume preflight
        # (1 inspect), and the isolated run re-inspection (1 inspect).
        self.assertEqual(log_text.count("docker image inspect"), 3)
        self.assertEqual(log_text.count("docker run"), 1)

    # --- Isolated (digest-pinned OCI) E2E ---

    def setup_candidate(self, work: Path, branch: str = "ship/topic-direct"):
        git(work, "switch", "-c", branch)
        write(work / "file.txt", "candidate change\n")
        git(work, "add", "file.txt")
        git(work, "commit", "-q", "-m", "test: direct candidate")
        candidate = git(work, "rev-parse", "HEAD")
        parent = git(work, "rev-parse", "HEAD^")
        tree = git(work, "rev-parse", "HEAD^{tree}")
        run_dir = work / ".git" / "ship-runs" / "run-direct-1"
        run_dir.mkdir(parents=True)
        (run_dir / "commit.json").write_text(json.dumps({
            "run_id": "run-direct-1",
            "sha": candidate,
            "remote": "origin",
            "ref": f"refs/heads/{branch}",
            "branch": branch,
            "parent": parent,
            "tree": tree,
            "type": "commit",
        }, indent=2) + "\n", encoding="utf-8")
        return candidate, run_dir

    def invoke_ship_deploy(self, work: Path, candidate: str, branch: str, env):
        zero = "0" * 40
        line = f"{candidate} {candidate} refs/heads/{branch} {zero}\n"
        return run([str(SHIP_DEPLOY)], cwd=work, input_text=line, env=env)

    def make_clean_path(self, fake_docker_bin: Path) -> str:
        clean = self.base / "clean-bin"
        clean.mkdir(parents=True, exist_ok=True)
        for tool in ("git", "python3", "bash", "grep", "cut", "cat", "rm",
                     "mkdir", "mv", "tr", "dirname", "basename", "mktemp"):
            found = shutil.which(tool)
            self.assertIsNotNone(found, f"host tool {tool} required for clean PATH")
            (clean / tool).symlink_to(found)
        (clean / "docker").symlink_to(fake_docker_bin / "docker")
        clean_path = str(clean)
        self.assertIsNone(shutil.which("node", path=clean_path))
        self.assertIsNone(shutil.which("npm", path=clean_path))
        self.assertIsNone(shutil.which("pnpm", path=clean_path))
        self.assertIsNone(shutil.which("yarn", path=clean_path))
        self.assertIsNone(shutil.which("bun", path=clean_path))
        return clean_path

    def test_isolated_success_exact_sha(self) -> None:
        work, remote = build_fixture(self.base, isolated=True)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        env, log = isolated_env(self.base)
        proc = run_ship_build(work, branch="ship/isolated-ok", env=env)
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        head = git(work, "rev-parse", "HEAD")
        self.assertEqual((work / ".ship" / "deploy-sha").read_text().strip(), head)
        run_dir = parse_run_dir(proc.stdout, work)
        deploy_receipt = json.loads((run_dir / "deploy.json").read_text())
        preflight_receipt = json.loads((run_dir / "preflight.json").read_text())
        self.assertEqual(deploy_receipt["e2e_mode"], "isolated_oci")
        self.assertEqual(deploy_receipt["e2e_image"], ISOLATED_IMAGE)
        self.assertEqual(deploy_receipt["e2e_image_id"], FAKE_IMAGE_ID)
        self.assertEqual(preflight_receipt["e2e_image_id"], FAKE_IMAGE_ID)
        self.assertEqual(preflight_receipt["sha"], head)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/isolated-ok"), head)
        log_text = log.read_text(encoding="utf-8")
        # Check before deploy before run, in that order.
        inspect_at = log_text.find("docker image inspect")
        deploy_at = log_text.find("deploy\n")
        run_at = log_text.find("docker run")
        self.assertTrue(0 <= inspect_at < deploy_at < run_at, log_text)
        self.assertIn("--pull never", log_text)
        self.assertIn("--network bridge", log_text)
        self.assertIn("--cap-drop ALL", log_text)
        self.assertIn("no-new-privileges", log_text)
        self.assertIn("--read-only", log_text)
        self.assertIn(ISOLATED_IMAGE, log_text)
        self.assertIn("npm run test:e2e", log_text)
        self.assertNotIn("--privileged", log_text)
        self.assertNotIn("docker.sock", log_text)
        self.assertNotIn("--network host", log_text)

    def test_isolated_missing_image_blocks_before_deploy_no_fallback(self) -> None:
        work, remote = build_fixture(self.base, isolated=True)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        env, log = isolated_env(self.base, mode="missing-image")
        proc = run_ship_build(work, branch="ship/isolated-missing", env=env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/isolated-missing"), "")
        # Preflight ran before rollout: the deploy entry never ran,
        # and there was no host fallback that would have run e2e.
        self.assertFalse((work / ".ship" / "deploy-sha").exists())
        self.assertNotIn("docker run", log.read_text(encoding="utf-8"))
        self.assertNotIn("e2e ok", proc.stdout + proc.stderr)

    def test_isolated_e2e_failure_blocks_upload_no_fallback(self) -> None:
        work, remote = build_fixture(self.base, isolated=True)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        env, _log = isolated_env(self.base, mode="e2e-fail")
        proc = run_ship_build(work, branch="ship/isolated-e2e-fail", env=env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("e2e failed", proc.stdout + proc.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/isolated-e2e-fail"), "")

    def test_isolated_image_changed_after_preflight_blocks(self) -> None:
        work, remote = build_fixture(self.base, isolated=True)
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        env, log = isolated_env(self.base, mode="image-changed")
        proc = run_ship_build(work, branch="ship/isolated-drift", env=env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("drift", proc.stdout + proc.stderr)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/isolated-drift"), "")
        # The drift was caught before the container run.
        self.assertNotIn("docker run", log.read_text(encoding="utf-8"))

    def test_isolated_tag_only_contract_blocks_before_mutation(self) -> None:
        work, remote = build_fixture(
            self.base, isolated=True, isolated_image="node:26.13.1-alpine"
        )
        before = git(work, "rev-parse", "HEAD")
        write(work / "file.txt", "changed\n")
        git(work, "add", "file.txt")
        env, _log = isolated_env(self.base)
        proc = run_ship_build(work, branch="ship/isolated-tag-only", env=env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(git(work, "rev-parse", "HEAD"), before)
        self.assertEqual(remote_sha(remote, "refs/heads/ship/isolated-tag-only"), "")

    def test_isolated_candidate_contract_invalid_blocks_before_deploy(self) -> None:
        work, _remote = build_fixture(self.base, isolated=True)
        # Bypass the doctor by committing an invalid contract
        # directly; ship-deploy must validate the candidate
        # contract itself and block before rollout, with no
        # host fallback.
        contract_path = work / ".ship" / "e2e-runner.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["runner"]["image"] = "node:26.13.1-alpine"
        contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        git(work, "add", ".ship/e2e-runner.json")
        # setup_candidate stages file.txt too; commit both together
        # by using it after staging the contract change.
        candidate, _run_dir = self.setup_candidate(work, branch="ship/topic-direct")
        env, log = isolated_env(self.base)
        proc = self.invoke_ship_deploy(work, candidate, "ship/topic-direct", env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse((work / ".ship" / "deploy-sha").exists())
        self.assertNotIn("docker run", log.read_text(encoding="utf-8"))

    def test_isolated_clean_host_path_without_node(self) -> None:
        work, _remote = build_fixture(self.base, isolated=True)
        candidate, run_dir = self.setup_candidate(work, branch="ship/topic-clean")
        env, log = isolated_env(self.base)
        clean_path = self.make_clean_path(self.base / "fake-bin")
        env["PATH"] = clean_path
        # The isolated E2E path must succeed with no host Node or
        # package manager in PATH at all.
        proc = self.invoke_ship_deploy(work, candidate, "ship/topic-clean", env)
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        deploy_receipt = json.loads((run_dir / "deploy.json").read_text())
        self.assertEqual(deploy_receipt["e2e_mode"], "isolated_oci")
        self.assertEqual(deploy_receipt["sha"], candidate)
        self.assertIn("docker run", log.read_text(encoding="utf-8"))

    def test_ship_skill_invocation_without_plugin(self) -> None:
        # Ship is invoked by loading the skill (ID `ship`) as `@ship`
        # with no arguments; no plugin dispatch executes.
        skill = (FLEET_ROOT / "fleet" / "skills" / "ship" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for required in (
            "@ship",
            "no arguments",
            "by ID `ship`",
            "No slash command is registered",
            "no routine approval stops",
            "ship-destination",
            "never broadened",
        ):
            self.assertIn(required, skill)
        self.assertNotIn("fleet/plugins/ship.ts", skill)
        self.assertNotIn("`/ship`", skill)
        self.assertFalse(
            (FLEET_ROOT / "fleet" / "plugins" / "ship.ts").exists()
        )


if __name__ == "__main__":
    unittest.main()
