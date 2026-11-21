#!/usr/bin/env python3
"""Fixture-only tests for scripts/ship/ship-doctor and the /ship workflow.

Stdlib only. Fixtures are built in a temporary directory and are never
executed; the doctor is only ever pointed at them as data.
"""

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCTOR = REPO_ROOT / "scripts" / "ship" / "ship-doctor"

EXPECTED_CHECK_IDS = [
    "path.safety",
    "layout.supported",
    "metadata.parse",
    "git.layout",
    "husky.hooks_path",
    "husky.pre_commit",
    "husky.commit_msg",
    "husky.pre_push",
    "husky.shim_pre_commit",
    "husky.shim_commit_msg",
    "husky.shim_pre_push",
    "husky.helper",
    "husky.dependency",
    "toolchain.pinned",
    "toolchain.lockfile",
    "disable_indicators",
    "scripts.prepare",
    "scripts.format_check",
    "scripts.lint",
    "scripts.test_unit",
    "scripts.test_e2e",
    "structure.wiring",
]

PASSING_PACKAGE = {
    "name": "fixture",
    "packageManager": "pnpm@10.18.1",
    "scripts": {
        "prepare": "husky",
        "format:check": "prettier --check .",
        "lint": "eslint .",
        "test:unit": "vitest run unit",
        "test:e2e": "playwright test",
    },
    "devDependencies": {"husky": "9.1.7"},
}

GIT_CONFIG = (
    "[core]\n"
    "\trepositoryformatversion = 0\n"
    "\tbare = false\n"
    "\thooksPath = .husky/_\n"
    '[remote "origin"]\n'
    "\turl = https://example.invalid/fixture.git\n"
)

SHIM = '#!/usr/bin/env sh\n. "$(dirname "$0")/h"\n'


def write_text(path: Path, text: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


def build_passing(root: Path) -> None:
    # Realistic Husky v9 shape (mirrors Companion): user hooks are
    # regular non-executable files run via sh; generated shims in
    # .husky/_ plus the _/h helper are executable. No _/husky.sh.
    write_text(root / "package.json", json.dumps(PASSING_PACKAGE, indent=2))
    write_text(root / "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
    write_text(root / ".husky" / "pre-commit", "pnpm test:unit\n")
    write_text(root / ".husky" / "commit-msg", "pnpm exec commitlint\n")
    write_text(root / ".husky" / "pre-push", "pnpm test:unit\n")
    write_text(root / ".husky" / "_" / "pre-commit", SHIM, executable=True)
    write_text(root / ".husky" / "_" / "commit-msg", SHIM, executable=True)
    write_text(root / ".husky" / "_" / "pre-push", SHIM, executable=True)
    write_text(
        root / ".husky" / "_" / "h",
        "#!/usr/bin/env sh\nsh -e \"$s\" \"$@\"\n",
    )
    write_text(root / ".git" / "HEAD", "ref: refs/heads/main\n")
    write_text(root / ".git" / "config", GIT_CONFIG)


def write_git_config(root: Path, text: str) -> None:
    write_text(root / ".git" / "config", text)


def run_doctor(target: Path) -> tuple[int, str, dict]:
    proc = subprocess.run(
        [sys.executable, str(DOCTOR), str(target)],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    payload = json.loads(proc.stdout)
    return proc.returncode, proc.stdout, payload


def digest_tree(root: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
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
        build_passing(self.root)

    def check_map(self, payload: dict) -> dict[str, dict]:
        return {entry["id"]: entry for entry in payload["checks"]}

    # --- outcomes ---

    def test_local_pass(self) -> None:
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 0)
        self.assertEqual(payload["result"], "local_pass")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["tool"], "ship-doctor")
        self.assertEqual(
            [entry["id"] for entry in payload["checks"]], EXPECTED_CHECK_IDS
        )
        self.assertTrue(
            all(entry["status"] == "pass" for entry in payload["checks"])
        )
        # User hooks are not executable in Husky v9 and still pass.
        self.assertFalse(
            (self.root / ".husky" / "pre-commit").stat().st_mode
            & stat.S_IXUSR
        )

    def test_blocked_missing_user_hook(self) -> None:
        (self.root / ".husky" / "pre-push").unlink()
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertEqual(payload["result"], "blocked")
        entry = self.check_map(payload)["husky.pre_push"]
        self.assertEqual((entry["status"], entry["reason"]), ("fail", "missing"))

    def test_blocked_missing_commit_msg(self) -> None:
        (self.root / ".husky" / "commit-msg").unlink()
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        entry = self.check_map(payload)["husky.commit_msg"]
        self.assertEqual(
            (entry["status"], entry["reason"]), ("fail", "missing")
        )

    def test_blocked_missing_shim_and_helper(self) -> None:
        (self.root / ".husky" / "_" / "pre-push").unlink()
        (self.root / ".husky" / "_" / "h").unlink()
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        checks = self.check_map(payload)
        self.assertEqual(checks["husky.shim_pre_push"]["reason"], "missing")
        self.assertEqual(checks["husky.helper"]["reason"], "missing")

    def test_blocked_non_executable_shim(self) -> None:
        shim = self.root / ".husky" / "_" / "pre-commit"
        shim.chmod(shim.stat().st_mode & ~stat.S_IXUSR)
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        entry = self.check_map(payload)["husky.shim_pre_commit"]
        self.assertEqual(
            (entry["status"], entry["reason"]), ("fail", "not_executable")
        )

    def test_blocked_disable_indicator(self) -> None:
        write_text(
            self.root / ".husky" / "pre-commit",
            "git commit --no-verify -m bypass\n",
        )
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        entry = self.check_map(payload)["disable_indicators"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("fail", "disable_indicator_present"),
        )

    def test_blocked_disable_indicator_in_scripts(self) -> None:
        package = json.loads((self.root / "package.json").read_text())
        package["scripts"]["lint"] = "eslint . # HUSKY=0"
        write_text(self.root / "package.json", json.dumps(package))
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        self.assertEqual(
            self.check_map(payload)["disable_indicators"]["reason"],
            "disable_indicator_present",
        )

    def test_blocked_missing_script(self) -> None:
        package = json.loads((self.root / "package.json").read_text())
        del package["scripts"]["test:e2e"]
        write_text(self.root / "package.json", json.dumps(package))
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        entry = self.check_map(payload)["scripts.test_e2e"]
        self.assertEqual(
            (entry["status"], entry["reason"]), ("fail", "script_missing")
        )

    def test_blocked_prepare_not_husky(self) -> None:
        package = json.loads((self.root / "package.json").read_text())
        package["scripts"]["prepare"] = "husky install"
        write_text(self.root / "package.json", json.dumps(package))
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        entry = self.check_map(payload)["scripts.prepare"]
        self.assertEqual(
            (entry["status"], entry["reason"]), ("fail", "script_not_husky")
        )

    def test_blocked_unpinned(self) -> None:
        package = json.loads((self.root / "package.json").read_text())
        del package["packageManager"]
        write_text(self.root / "package.json", json.dumps(package))
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        entry = self.check_map(payload)["toolchain.pinned"]
        self.assertEqual(
            (entry["status"], entry["reason"]), ("fail", "unpinned")
        )

    def test_blocked_lockfile_mismatch(self) -> None:
        (self.root / "pnpm-lock.yaml").rename(
            self.root / "package-lock.json"
        )
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        entry = self.check_map(payload)["toolchain.lockfile"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("fail", "lockfile_mismatch"),
        )

    def test_npm_corresponding_lockfile_passes(self) -> None:
        package = json.loads((self.root / "package.json").read_text())
        package["packageManager"] = "npm@10.8.2"
        write_text(self.root / "package.json", json.dumps(package))
        (self.root / "pnpm-lock.yaml").rename(
            self.root / "package-lock.json"
        )
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 0)
        self.assertEqual(payload["result"], "local_pass")

    def test_blocked_missing_husky_dependency(self) -> None:
        package = json.loads((self.root / "package.json").read_text())
        del package["devDependencies"]
        write_text(self.root / "package.json", json.dumps(package))
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        entry = self.check_map(payload)["husky.dependency"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("fail", "husky_dependency_missing"),
        )

    # --- Git layout / declared hooks path ---

    def test_blocked_hooks_path_missing(self) -> None:
        write_git_config(self.root, "[core]\n\tbare = false\n")
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        entry = self.check_map(payload)["husky.hooks_path"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("fail", "hooks_path_missing"),
        )

    def test_blocked_hooks_path_mismatch(self) -> None:
        write_git_config(
            self.root, "[core]\n\tbare = false\n\thooksPath = .husky\n"
        )
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 1)
        entry = self.check_map(payload)["husky.hooks_path"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("fail", "hooks_path_mismatch"),
        )

    def test_indeterminate_git_missing(self) -> None:
        import shutil

        shutil.rmtree(self.root / ".git")
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        checks = self.check_map(payload)
        self.assertEqual(checks["git.layout"]["status"], "unknown")
        self.assertEqual(checks["husky.hooks_path"]["status"], "unknown")

    def test_indeterminate_git_file_linked(self) -> None:
        import shutil

        shutil.rmtree(self.root / ".git")
        write_text(self.root / ".git", "gitdir: /elsewhere\n")
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        self.assertEqual(payload["result"], "indeterminate")

    def test_indeterminate_git_bare(self) -> None:
        write_git_config(
            self.root,
            "[core]\n\tbare = true\n\thooksPath = .husky/_\n",
        )
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        self.assertEqual(
            self.check_map(payload)["git.layout"]["reason"],
            "unsupported_layout",
        )

    def test_indeterminate_git_include(self) -> None:
        write_git_config(
            self.root,
            "[core]\n\tbare = false\n\thooksPath = .husky/_\n"
            '[include]\n\tpath = /elsewhere/config\n',
        )
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        self.assertEqual(payload["result"], "indeterminate")

    def test_indeterminate_git_config_malformed(self) -> None:
        write_git_config(self.root, "not a config\n")
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        self.assertEqual(payload["result"], "indeterminate")

    # --- indeterminate: unsafe paths, malformed / untrusted metadata ---

    def test_indeterminate_missing_package_json(self) -> None:
        (self.root / "package.json").unlink()
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        entry = self.check_map(payload)["layout.supported"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("unknown", "unsupported_layout"),
        )

    def test_indeterminate_malformed_package_json(self) -> None:
        write_text(self.root / "package.json", "{not json")
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        entry = self.check_map(payload)["metadata.parse"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("unknown", "malformed_metadata"),
        )

    def test_indeterminate_non_object_package_json(self) -> None:
        write_text(self.root / "package.json", '["array"]')
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)

    def test_indeterminate_malformed_scripts(self) -> None:
        package = json.loads((self.root / "package.json").read_text())
        package["scripts"] = "not-an-object"
        write_text(self.root / "package.json", json.dumps(package))
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        entry = self.check_map(payload)["scripts.test_e2e"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("unknown", "malformed_metadata"),
        )

    def test_indeterminate_nonexistent_path(self) -> None:
        code, _, payload = run_doctor(Path(self._tmp.name) / "does-not-exist")
        self.assertEqual(code, 2)
        entry = self.check_map(payload)["path.safety"]
        self.assertEqual(
            (entry["status"], entry["reason"]), ("unknown", "unsafe_path")
        )

    def test_indeterminate_file_not_directory(self) -> None:
        target = Path(self._tmp.name) / "a-file"
        write_text(target, "x")
        code, _, payload = run_doctor(target)
        self.assertEqual(code, 2)
        self.assertEqual(
            self.check_map(payload)["path.safety"]["reason"], "unsafe_path"
        )

    def test_indeterminate_symlink_root(self) -> None:
        link = Path(self._tmp.name) / "link"
        os.symlink(self.root, link)
        code, _, payload = run_doctor(link)
        self.assertEqual(code, 2)

    def test_indeterminate_ancestor_symlink(self) -> None:
        link = Path(self._tmp.name) / "ancestor-link"
        os.symlink(self.root.parent, link)
        code, _, payload = run_doctor(link / "repo")
        self.assertEqual(code, 2)
        entry = self.check_map(payload)["path.safety"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("unknown", "symlink_not_allowed"),
        )

    def test_indeterminate_in_tree_symlink_package_json(self) -> None:
        write_text(self.root / "inner.json", json.dumps(PASSING_PACKAGE))
        (self.root / "package.json").unlink()
        os.symlink("inner.json", self.root / "package.json")
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        entry = self.check_map(payload)["metadata.parse"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("unknown", "symlink_not_allowed"),
        )

    def test_indeterminate_ancestor_symlink_husky_underscore(self) -> None:
        import shutil

        shutil.rmtree(self.root / ".husky" / "_")
        (self.root / "real-underscore").mkdir()
        for name in ("pre-commit", "commit-msg", "pre-push", "h"):
            write_text(self.root / "real-underscore" / name, SHIM, executable=True)
        os.symlink("real-underscore", self.root / ".husky" / "_")
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        checks = self.check_map(payload)
        self.assertEqual(
            checks["husky.shim_pre_commit"]["status"], "unknown"
        )
        self.assertEqual(
            checks["husky.hooks_path"]["status"], "unknown"
        )

    def test_indeterminate_fifo_package_json(self) -> None:
        (self.root / "package.json").unlink()
        os.mkfifo(self.root / "package.json")
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        entry = self.check_map(payload)["metadata.parse"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("unknown", "nonregular_file"),
        )

    def test_indeterminate_fifo_hook(self) -> None:
        (self.root / ".husky" / "pre-commit").unlink()
        os.mkfifo(self.root / ".husky" / "pre-commit")
        code, _, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        entry = self.check_map(payload)["husky.pre_commit"]
        self.assertEqual(
            (entry["status"], entry["reason"]),
            ("unknown", "nonregular_file"),
        )

    def test_indeterminate_oversized_package_json_capped(self) -> None:
        secret = "SECRET-BEYOND-CAP-12345"
        package = json.loads((self.root / "package.json").read_text())
        package["padding"] = "x" * (1_048_576 + 1)
        package["after"] = secret
        write_text(self.root / "package.json", json.dumps(package))
        code, output, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        self.assertNotIn(secret, output)
        entry = self.check_map(payload)["metadata.parse"]
        self.assertEqual(
            (entry["status"], entry["reason"]), ("unknown", "oversized")
        )

    def test_indeterminate_oversized_hook_capped(self) -> None:
        secret = "SECRET-HOOK-BEYOND-CAP"
        write_text(
            self.root / ".husky" / "pre-commit",
            "x" * 65_536 + secret + "\n",
        )
        code, output, payload = run_doctor(self.root)
        self.assertEqual(code, 2)
        self.assertNotIn(secret, output)
        entry = self.check_map(payload)["husky.pre_commit"]
        self.assertEqual(
            (entry["status"], entry["reason"]), ("unknown", "oversized")
        )

    def test_usage_requires_explicit_path(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(DOCTOR)],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 2)

    # --- read-only, unchanged fixtures, redaction ---

    def test_fixtures_unchanged_and_secrets_redacted(self) -> None:
        secret = "SECRET-TOKEN-9f8e7d6c"
        package = json.loads((self.root / "package.json").read_text())
        package["scripts"]["lint"] = f"eslint . # {secret}"
        package["name"] = f"fixture-{secret}"
        write_text(self.root / "package.json", json.dumps(package))
        write_text(
            self.root / ".husky" / "pre-commit",
            f"run-check # {secret}\n",
        )
        write_text(self.root / ".env", f"TOKEN={secret}\n")
        write_git_config(
            self.root,
            "[core]\n\tbare = false\n\thooksPath = .husky/_\n"
            f'[remote "origin"]\n\turl = {secret}\n',
        )
        before = digest_tree(self.root)
        code, output, payload = run_doctor(self.root)
        after = digest_tree(self.root)
        self.assertEqual(code, 0)
        self.assertEqual(payload["result"], "local_pass")
        self.assertEqual(before, after)
        self.assertNotIn(secret, output)
        self.assertNotIn("TOKEN=", output)
        self.assertNotIn("example.invalid", output)

    def test_doctor_uses_no_forbidden_mechanisms(self) -> None:
        source = DOCTOR.read_text(encoding="utf-8")
        for banned in (
            "subprocess",
            "socket",
            "urllib",
            "requests",
            "os.system",
            "os.popen",
            "os.exec",
            "os.spawn",
            "os.fork",
            "eval(",
            "exec(",
            "shutil",
            "http.client",
            "read_text",
            ".resolve(",
            "lstat",
            "Path(",
        ):
            self.assertNotIn(banned, source)

    # --- scaffold: ship skill and server plugin ---

    def test_ship_skill_frontmatter_and_steps(self) -> None:
        text = (
            REPO_ROOT / "fleet" / "skills" / "ship" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text[4:].split("\n---\n", 1)[0]
        self.assertIn("name: Ship", frontmatter)
        self.assertIn("opencode/autoinvoke: false", frontmatter)
        for required in (
            "Step 1 - Run the ship-doctor script",
            "Step 2 - Validate the state of the current environment",
            "Step 3 - Run the ship-build script",
            "Step 4 - Run the ship-deploy script",
            "Step 5 - Create a PR",
            "scripts/ship/ship-build",
            "scripts/ship/ship-deploy",
            "scripts/ship/ship-destination",
            "test:e2e",
            "no implicit staging",
            "nested in the Step 3 push",
            "@ship",
            "no routine approval stops",
            "staged_empty",
            "busy lease",
            "single reviewed auto-staging",
            "exact reviewed paths",
            "reruns the same destination",
            "never broadened",
            "without needing a terminal",
            "task-owned provenance",
            "known clean baseline",
            "later @ship in the same session",
            "no user-supplied path list",
            "safe derived topic",
            "no publish or commit directly to",
            "never stages on `main`",
            "git switch -c <topic>",
            "git branch --show-current",
            "before any staging",
        ):
            self.assertIn(required, text)
        for banned in ("!`", "$(", "${", "Cal asks the user first",
                       "off-main requires an explicit",
                       "only if starting off main",
                       "explicit include",
                       "workflow stays staged-only",
                       "empty index on a topic branch only"):
            self.assertNotIn(banned, text)

    def test_ship_skill_main_staging_eligible_with_provenance(self) -> None:
        text = (
            REPO_ROOT / "fleet" / "skills" / "ship" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("eligible topic branch or, on `main`", text)
        self.assertIn("task-owned provenance", text)
        self.assertIn("known clean baseline", text)
        self.assertIn("later @ship in the same session", text)
        self.assertIn("no user-supplied path list", text)
        self.assertIn("safe derived topic", text)
        self.assertIn("never a publish or commit directly to", text)
        self.assertIn("never broadened", text)
        # Branch-before-staging on main: creation precedes any add,
        # the carry is revalidated, and the rerun must match.
        self.assertIn("never stages on `main`", text)
        self.assertIn("git switch -c <topic>", text)
        self.assertIn("before any staging", text)
        self.assertIn("branches before editing", text)
        self.assertIn("git branch --show-current", text)
        self.assertIn("exactly the branch just created/checked out", text)
        # The old topic-only exclusion is gone on both branches:
        # topic behavior is preserved, main is eligible with
        # established provenance, and no separate approval or
        # user-supplied list is required when provenance is known.
        self.assertNotIn("workflow stays staged-only", text)
        self.assertNotIn("explicit include", text)
        self.assertNotIn("empty index on a topic branch only", text)
        self.assertIn("stages nothing and returns a scope blocker", text)
        self.assertIn("likely secret or otherwise unsafe", text)
        self.assertIn("one rerun", text.lower())

    def test_ship_skill_invocation_without_plugin(self) -> None:
        text = (
            REPO_ROOT / "fleet" / "skills" / "ship" / "SKILL.md"
        ).read_text(encoding="utf-8")
        for required in (
            "ID `ship`",
            "frontmatter name `Ship`",
            "@ship",
            "no arguments",
            "No slash command is registered",
            "no routine approval stops",
            "busy or unverifiable required lease",
            "staged_empty",
            "never broadened",
            "ship-destination",
        ):
            self.assertIn(required, text)
        for banned in (
            "fleet/plugins/ship.ts",
            "fleet.ship",
            "ctx.command.transform",
            "ctx.session.prompt",
            "`/ship`",
        ):
            self.assertNotIn(banned, text)
        self.assertFalse(
            (REPO_ROOT / "fleet" / "plugins" / "ship.ts").exists()
        )

    def test_ship_docs_describe_standard(self) -> None:
        text = (REPO_ROOT / "docs" / "ship.md").read_text(encoding="utf-8")
        for required in (
            "strict opt-in",
            "Husky alone",
            "the repository’s E2E suite must finish successfully",
            "scripts/ship/ship-doctor",
            "scripts/ship/ship-build",
            "scripts/ship/ship-deploy",
            "local_pass",
            "blocked",
            "indeterminate",
            "test:e2e",
            "no per-repo config",
            "production deploy skill",
            "scripts/ship/ship-destination",
            "no routine approval stops",
            "single configured remote",
            "busy lease",
            "needs no confirmation",
            "local main",
            "no rewritten commits",
            "duplicated hooks",
            "approved mapping",
            "local structural validation",
            "Web/native dispatch",
            "absolute",
            "trusted",
            "Step 1 - Run the ship-doctor script",
            "Step 5 - Create a PR",
            "nested in",
            "fleet/skills/ship/SKILL.md",
            "fleet/skills/ship/resources/PR_TEMPLATE.md",
            "scripts/ship-deploy",
            "post-push",
            "cannot prevent",
            "Companion",
            "@ship",
            "single reviewed Worker staging",
            "never broadened",
            "task-owned provenance",
            "known clean baseline",
            "later @ship in the same session",
            "user-supplied path list",
            "safe derived topic",
            "no publish or commit directly to",
            "never stages on `main`",
            "git switch -c <topic>",
            "git branch --show-current",
            "branches before editing",
        ):
            self.assertIn(required, text)
        self.assertNotIn("paid", text.lower())
        self.assertNotIn("python3 scripts/ship-doctor", text)
        self.assertNotIn("Shipping is not implemented yet", text)
        self.assertNotIn("fleet/plugins/ship.ts", text)
        self.assertNotIn("`/ship`", text)

    def test_ship_docs_main_staging_eligible_with_provenance(self) -> None:
        text = (REPO_ROOT / "docs" / "ship.md").read_text(encoding="utf-8")
        self.assertIn("task-owned provenance", text)
        self.assertIn("known clean baseline", text)
        self.assertIn("later @ship in the same session", text)
        self.assertIn("user-supplied path list", text)
        self.assertIn("safe derived topic", text)
        self.assertIn("no publish or commit directly", text.lower())
        self.assertIn("never stages on `main`", text)
        self.assertIn("git switch -c <topic>", text)
        self.assertIn("git branch --show-current", text)
        self.assertIn("branches before editing", text)
        self.assertIn("exactly the branch just created/checked out", text)
        self.assertNotIn("explicit include", text)
        self.assertNotIn("on `main` only staged work ships", text)

    def test_fleet_agents_ship_bound_branch_before_editing(self) -> None:
        text = (REPO_ROOT / "fleet" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("ship-bound", text)
        self.assertIn("docs/ship.md", text)
        self.assertIn("never stage on `main`", text)
        self.assertIn("scoped to ship-bound work only", text)

    def test_pr_template_filled(self) -> None:
        text = (
            REPO_ROOT
            / "fleet"
            / "skills"
            / "ship"
            / "resources"
            / "PR_TEMPLATE.md"
        ).read_text(encoding="utf-8")
        self.assertTrue(len(text.strip()) > 100)
        for required in ("Candidate SHA", "test:e2e", "git ls-remote"):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
