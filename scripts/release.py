#!/usr/bin/env -S uv run
"""release.py — Bump version, commit, tag, and push.

Usage:
    ./scripts/release.py patch
    ./scripts/release.py minor
    ./scripts/release.py major
    ./scripts/release.py pre patch [dev|rc]  # from stable: bump patch + start pre-release
    ./scripts/release.py pre minor [dev|rc]  # from stable: bump minor + start pre-release
    ./scripts/release.py pre major [dev|rc]  # from stable: bump major + start pre-release
    ./scripts/release.py pre [dev|rc]        # from pre-release: promote phase or increment
    ./scripts/release.py pre                 # from pre-release: increment counter
    ./scripts/release.py release             # strip pre-release suffix → stable
    ./scripts/release.py set 1.2.3           # set explicit version
    ./scripts/release.py patch --dry-run
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from semver import Version

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------
BOLD  = "\033[1m"
GREEN = "\033[32m"
CYAN  = "\033[36m"
YELLOW = "\033[33m"
RED   = "\033[31m"
RESET = "\033[0m"

def ok(msg: str)   -> None: print(f"  {GREEN}✔{RESET} {msg}")
def err(msg: str)  -> None: print(f"  {RED}✗{RESET} {msg}", file=sys.stderr)
def warn(msg: str) -> None: print(f"  {YELLOW}!{RESET} {msg}")

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent

PYPROJECT_FILES: list[Path] = [
    REPO_ROOT / "pyproject.toml",
    REPO_ROOT / "apps" / "tg-jenkins-bot"      / "pyproject.toml",
    REPO_ROOT / "apps" / "build-manager"        / "pyproject.toml",
    REPO_ROOT / "apps" / "config-hub"           / "pyproject.toml",
    REPO_ROOT / "apps" / "file-manager"         / "pyproject.toml",
    REPO_ROOT / "apps" / "agent-control"        / "pyproject.toml",
    REPO_ROOT / "apps" / "tg-admin-bot"         / "pyproject.toml",
    REPO_ROOT / "libs" / "config-schema"        / "pyproject.toml",
]

VERSION_RE = re.compile(r'^(version\s*=\s*")[^"]+(")', re.MULTILINE)

# ---------------------------------------------------------------------------
# Version I/O
# ---------------------------------------------------------------------------

def _extract_version(path: Path) -> str:
    m = VERSION_RE.search(path.read_text())
    if not m:
        raise SystemExit(f"{RED}error:{RESET} no version field found in {path.relative_to(REPO_ROOT)}")
    return m.group(0).split('"')[1]


def read_current_version() -> str:
    """Read version from root pyproject.toml and warn if any member diverges."""
    versions = {p: _extract_version(p) for p in PYPROJECT_FILES}
    root_ver = versions[PYPROJECT_FILES[0]]

    diverged = {p: v for p, v in versions.items() if v != root_ver}
    if diverged:
        warn("Version mismatch detected across workspace members:")
        for p, v in versions.items():
            marker = f"{YELLOW}←{RESET}" if p in diverged else " "
            print(f"    {marker}  {p.relative_to(REPO_ROOT)}: {v}")
        print()
        answer = input("  Force-unify all to the root version before continuing? [y/N]: ").strip().lower()
        if answer != "y":
            raise SystemExit("Aborted.")
        for p in diverged:
            _write_one(p, root_ver)
        ok(f"Unified all files to {root_ver}.")
        print()

    return root_ver


def _write_one(path: Path, version: str) -> None:
    text = path.read_text()
    updated = VERSION_RE.sub(rf'\g<1>{version}\g<2>', text, count=1)
    path.write_text(updated)


def write_version(version: str) -> None:
    for p in PYPROJECT_FILES:
        _write_one(p, version)

# ---------------------------------------------------------------------------
# Version computation
# ---------------------------------------------------------------------------

_BASE_BUMPS = {"patch", "minor", "major"}


def compute_next(current: str, cmd: str, base: str | None, label: str | None) -> str:
    """Compute the next version string.

    For ``pre`` from a stable version, ``base`` (patch/minor/major) is required
    so we know which version component to target (cider semantics).
    From a pre-release, ``base`` is ignored and ``label`` controls phase promotion.
    """
    v = Version.parse(current)
    match cmd:
        case "patch":
            return str(v.bump_patch())
        case "minor":
            return str(v.bump_minor())
        case "major":
            return str(v.bump_major())
        case "pre":
            if v.prerelease is None:
                # Starting from stable: must specify which component to target.
                match base:
                    case "patch":
                        v = v.bump_patch()
                    case "minor":
                        v = v.bump_minor()
                    case "major":
                        v = v.bump_major()
                    case _:
                        raise SystemExit(
                            f"  {RED}error:{RESET} starting a pre-release from a stable version "
                            f"requires a base bump.\n"
                            f"  Usage: pre patch|minor|major [dev|rc]"
                        )
            return str(v.bump_prerelease(label))
        case "release":
            if v.prerelease is None:
                raise SystemExit(f"{RED}error:{RESET} '{current}' is already a stable version.")
            return str(v.finalize_version())
        case "set":
            if label is None:
                raise SystemExit(f"{RED}error:{RESET} 'set' requires a version argument.")
            return str(Version.parse(label))
        case _:
            raise SystemExit(f"{RED}error:{RESET} unknown command '{cmd}'.")

# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        cmd_str = " ".join(args)
        print(f"\n  {RED}✗ git error:{RESET} {cmd_str}", file=sys.stderr)
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                print(f"    {line}", file=sys.stderr)
        raise SystemExit(result.returncode)


def git_commit_tag(version: str) -> None:
    tag = f"v{version}"
    lock_file = REPO_ROOT / "uv.lock"
    _run(["git", "add"] + [str(p) for p in PYPROJECT_FILES] + [str(lock_file)])
    _run(["git", "commit", "-m", f"chore: bump version to {tag}"])
    _run(["git", "tag", tag])


def git_push(version: str) -> None:
    tag = f"v{version}"
    _run(["git", "push"])
    _run(["git", "push", "origin", tag])


def assert_tag_free(version: str) -> None:
    """Fail early (before any file writes) if the tag already exists locally or on remote."""
    tag = f"v{version}"

    # Local check
    local = subprocess.run(
        ["git", "tag", "--list", tag],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if local.stdout.strip():
        raise SystemExit(
            f"  {RED}✗ tag {tag} already exists locally.{RESET}\n"
            f"    Delete it first:  git tag -d {tag}"
        )

    # Remote check
    remote = subprocess.run(
        ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if remote.stdout.strip():
        raise SystemExit(
            f"  {RED}✗ tag {tag} already exists on remote.{RESET}\n"
            f"    Delete it there:  git push origin --delete {tag}"
        )


def github_actions_url() -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True, cwd=REPO_ROOT,
        )
        url = result.stdout.strip()
        # ssh → https
        url = re.sub(r"git@github\.com:", "https://github.com/", url)
        url = re.sub(r"\.git$", "", url)
        return f"{url}/actions"
    except Exception:
        return "https://github.com"

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def confirm(prompt: str) -> bool:
    return input(f"\n  {prompt} [y/N]: ").strip().lower() == "y"


def describe(cmd: str, base: str | None, label: str | None) -> str:
    """Human-readable summary of the bump operation."""
    match cmd:
        case "pre":
            parts = [p for p in (base, label) if p]
            detail = " ".join(parts) if parts else "increment"
            return f"pre-release ({detail})"
        case "release":
            return "release (finalize)"
        case "set":
            return f"set to {label}"
        case _:
            return cmd


# ---------------------------------------------------------------------------
# Interactive menu (no-argument mode)
# ---------------------------------------------------------------------------

_PRE_PHASES = ["dev", "rc"]  # ordered; rc is the last phase before release

# Type alias for menu rows: (display_label, cmd, base, label)
_MenuItem = tuple[str, str, str | None, str | None]


def _menu_items(current: str) -> list[_MenuItem]:
    """Return all valid mutations for the current version."""
    v = Version.parse(current)
    items: list[_MenuItem] = []

    if v.prerelease is not None:
        pre_label = v.prerelease.split(".")[0]   # e.g. "dev" or "rc"

        # Increment counter (same phase)
        items.append(("pre        ", "pre", None, None))

        # Promote to next phase
        if pre_label in _PRE_PHASES:
            idx = _PRE_PHASES.index(pre_label)
            if idx + 1 < len(_PRE_PHASES):
                next_phase = _PRE_PHASES[idx + 1]
                items.append((f"pre {next_phase}      ", "pre", None, next_phase))

        # Finalize to stable
        items.append(("release    ", "release", None, None))

        # Stable bumps (abandon pre-release)
        items.append(("patch      ", "patch", None, None))
        items.append(("minor      ", "minor", None, None))
        items.append(("major      ", "major", None, None))
    else:
        # Stable bumps
        items.append(("patch          ", "patch", None, None))
        items.append(("minor          ", "minor", None, None))
        items.append(("major          ", "major", None, None))
        # Pre-release options: each base × each phase
        for b in ("patch", "minor", "major"):
            for phase in _PRE_PHASES:
                items.append((f"pre {b} {phase}  ", "pre", b, phase))

    return items


def pick_from_menu(current: str) -> tuple[str, str | None, str | None]:
    """Display all mutations and return the chosen (cmd, base, label)."""
    items = _menu_items(current)

    print(f"\n  Current: {BOLD}{current}{RESET}\n")
    for i, (display, cmd, base, lbl) in enumerate(items, 1):
        next_ver = compute_next(current, cmd, base, lbl)
        print(f"  {CYAN}{i}{RESET}  {display}  {BOLD}{current}{RESET}  →  {BOLD}{next_ver}{RESET}")
    print()

    while True:
        raw = input(f"  Choose [1–{len(items)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            _, cmd, base, lbl = items[int(raw) - 1]
            return cmd, base, lbl
        print(f"  {YELLOW}Please enter a number between 1 and {len(items)}.{RESET}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bump monorepo version and push a git tag.",
        epilog="Run with no arguments for an interactive menu of all valid mutations.",
    )
    parser.add_argument("command", nargs="?", choices=["patch", "minor", "major", "pre", "release", "set"])
    parser.add_argument("token", nargs="?", help="For pre: base bump (patch/minor/major) or phase label (dev/rc). For set: target version.")
    parser.add_argument("extra", nargs="?", help="For pre from stable: phase label (dev/rc) when token is the base bump.")
    parser.add_argument("--dry-run", action="store_true", help="Print next version and exit (requires command)")
    args = parser.parse_args()

    # Resolve command, base bump, and pre-release label
    current = read_current_version()
    cmd: str
    pre_base: str | None = None
    pre_label: str | None = None

    if args.command is None:
        if args.dry_run:
            raise SystemExit(f"{RED}error:{RESET} --dry-run requires an explicit command.")
        cmd, pre_base, pre_label = pick_from_menu(current)
    else:
        cmd = args.command
        if cmd == "pre" and args.token in _BASE_BUMPS:
            # pre patch dev  /  pre minor rc  /  pre major
            pre_base = args.token
            pre_label = args.extra
        else:
            # pre dev  /  pre rc  /  pre  /  set 1.2.3  /  patch  etc.
            pre_label = args.token

    try:
        new = compute_next(current, cmd, pre_base, pre_label)
    except (ValueError, TypeError) as e:
        raise SystemExit(f"{RED}error:{RESET} {e}")

    # --dry-run: machine-readable, no interaction
    if args.dry_run:
        print(f"{current} → {new}")
        return

    # Pre-flight: fail before touching anything if the tag already exists
    assert_tag_free(new)

    # Summary line
    print(f"\n  {BOLD}{current}{RESET}  →  {BOLD}{CYAN}{new}{RESET}  ({describe(cmd, pre_base, pre_label)})\n")

    if not confirm("Commit and tag?"):
        raise SystemExit("Aborted.")

    write_version(new)
    ok("Syncing uv.lock and .venv…")
    _run(["uv", "sync"])
    git_commit_tag(new)
    ok("Done.")

    if not confirm("Push to origin and trigger CI?"):
        print(f"\n  {YELLOW}Tag v{new} is local. Push manually when ready:{RESET}")
        print(f"    git push && git push origin v{new}")
        return

    git_push(new)
    ok(f"Pushed. Watch: {github_actions_url()}")
    print()


if __name__ == "__main__":
    main()
