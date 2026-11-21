#!/usr/bin/env python3
"""Fixture tests for scripts/ship/ship-doctor (stdlib only)."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FLEET_ROOT = Path(__file__).resolve().parent.parent
DOCTOR = FLEET_ROOT / "scripts" / "ship" / "ship-doctor"
DEPLOY_WRAPPER = FLEET_ROOT / "scripts" / "ship" / "ship-deploy"

PASSING_PACKAGE = {
    "name": "fixture",
    "packageManager": "pnpm@10.18.1",
    "scripts": {
        "prepare": "husky",
        "format:check": "prettier --check .",
        "lint": "eslint .",
        "test:unit": "node --test",
        "test:e2e": "node scripts/test-e2e.mjs",
    },
    "devDependencies": {"husky": "9.1.7"},
}

SHIM = '#!/usr/bin/env sh\n. "$(dirname "$0")/h"\n'
HUSKY_HELPER = '#!/usr/bin/env sh\nsh -e "$(dirname "$0")/../$(basename "$0")" "$@"\n'


def write_text(path: Path, text: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def build_ready_repo(root: Path) -> None:
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "core.hooksPath", ".husky/_")
    git(root, "remote", "add", "origin", "https://github.com/example/fixture.git")

    write_text(root / "package.json", json.dumps(PASSING_PACKAGE, indent=2) + "\n")
    write_text(root / "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
    write_text(root / ".husky" / "pre-commit", "pnpm run format:check\n")
    write_text(root / ".husky" / "commit-msg", "true\n")
    write_text(root / ".husky" / "pre-push", f'#!/bin/sh\nexec "{DEPLOY_WRAPPER}"\n')
    write_text(root / ".husky" / "_" / "pre-commit", SHIM, executable=True)
    write_text(root / ".husky" / "_" / "commit-msg", SHIM, executable=True)
    write_text(root / ".husky" / "_" / "pre-push", SHIM, executable=True)
    write_text(root / ".husky" / "_" / "h", HUSKY_HELPER)
    write_text(
        root / "scripts" / "ship-deploy",
        '#!/usr/bin/env bash\nprintf "SHIP_DEPLOYED_SHA=%s\\n" "$1"\n',
        executable=True,
    )

    git(root, "add", ".")
    git(root, "commit", "--no-verify", "-m", "chore: initial fixture")


def run_doctor(
    target: Path, *, env_extra: dict[str, str] | None = None
) -> tuple[int, dict]:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(DOCTOR), str(target)],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    return proc.returncode, json.loads(proc.stdout)


def digest_tree(root: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts:
            continue
        if path.is_file() and not path.is_symlink():
            digests[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return digests


class ShipDoctorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir()
        build_ready_repo(self.root)

    def issue_ids(self, payload: dict) -> set[str]:
        return {item["id"] for item in payload["issues"]}

    def test_ready_and_read_only(self) -> None:
        before = digest_tree(self.root)
        code, payload = run_doctor(self.root)
        after = digest_tree(self.root)
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["package_manager"], "pnpm")
        self.assertEqual(payload["issues"], [])
        self.assertEqual(before, after)

    def test_not_a_git_repo(self) -> None:
        plain = Path(self._tmp.name) / "plain"
        plain.mkdir()
        code, payload = run_doctor(plain)
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "not_ready")
        self.assertIn("git.repo", self.issue_ids(payload))

    def test_missing_main_branch(self) -> None:
        git(self.root, "branch", "-m", "main", "develop")
        code, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertIn("git.repo", self.issue_ids(payload))

    def test_non_github_remote(self) -> None:
        git(self.root, "remote", "set-url", "origin", "https://gitlab.example/x/y.git")
        code, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertIn("git.remote", self.issue_ids(payload))

    def test_unpinned_package_manager_and_missing_lockfile(self) -> None:
        (self.root / "pnpm-lock.yaml").unlink()
        code, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertIn("toolchain.package_manager", self.issue_ids(payload))

        pkg = dict(PASSING_PACKAGE)
        pkg["packageManager"] = "pnpm"
        write_text(self.root / "package.json", json.dumps(pkg))
        code, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertIn("toolchain.package_manager", self.issue_ids(payload))

    def test_nvmrc_pin_missing_vs_installed(self) -> None:
        write_text(self.root / ".nvmrc", "99.88.77\n")
        fake_nvm = Path(self._tmp.name) / "nvm"
        code, payload = run_doctor(self.root, env_extra={"NVM_DIR": str(fake_nvm)})
        self.assertEqual(code, 1)
        self.assertIn("toolchain.node_pin", self.issue_ids(payload))

        fake_node = fake_nvm / "versions" / "node" / "v99.88.77" / "bin" / "node"
        write_text(fake_node, "#!/bin/sh\necho v99.88.77\n", executable=True)
        code, payload = run_doctor(self.root, env_extra={"NVM_DIR": str(fake_nvm)})
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "ready")

    def test_missing_required_script(self) -> None:
        pkg = json.loads((self.root / "package.json").read_text(encoding="utf-8"))
        del pkg["scripts"]["test:e2e"]
        write_text(self.root / "package.json", json.dumps(pkg))
        code, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertIn("scripts.required", self.issue_ids(payload))

    def test_husky_hooks_path_and_shims(self) -> None:
        git(self.root, "config", "core.hooksPath", ".githooks")
        code, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertIn("husky.installed", self.issue_ids(payload))

        git(self.root, "config", "core.hooksPath", ".husky/_")
        shim = self.root / ".husky" / "_" / "pre-push"
        shim.chmod(shim.stat().st_mode & ~stat.S_IXUSR)
        code, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertIn("husky.installed", self.issue_ids(payload))

    def test_pre_push_delegation_and_bypass_detection(self) -> None:
        write_text(
            self.root / ".husky" / "pre-push",
            f'# exec "{DEPLOY_WRAPPER}"\necho noop\n',
        )
        code, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertIn("husky.pre_push", self.issue_ids(payload))

        write_text(
            self.root / ".husky" / "pre-push",
            f'#!/bin/sh\nexec "{DEPLOY_WRAPPER}"\n',
        )
        write_text(
            self.root / ".husky" / "pre-commit",
            "git commit --no-verify\n",
        )
        code, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertIn("husky.pre_push", self.issue_ids(payload))

    def test_missing_or_non_executable_deploy_script(self) -> None:
        deploy = self.root / "scripts" / "ship-deploy"
        deploy.chmod(deploy.stat().st_mode & ~stat.S_IXUSR)
        code, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertIn("deploy.script", self.issue_ids(payload))

        deploy.unlink()
        code, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertIn("deploy.script", self.issue_ids(payload))

    def test_usage_error_exits_2(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(DOCTOR)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
