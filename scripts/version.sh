#!/usr/bin/env bash
# version.sh — Bump version across all pyproject.toml files, commit, tag, and push.
#
# Usage:
#   ./scripts/version.sh patch          # v0.2.0 → v0.2.1
#   ./scripts/version.sh minor          # v0.2.0 → v0.3.0
#   ./scripts/version.sh major          # v0.2.0 → v1.0.0
#   ./scripts/version.sh 1.5.0          # set explicit version
#   ./scripts/version.sh patch --dry-run  # preview without committing
#
# The current version is read from the latest git tag (the single source of truth).
# All three pyproject.toml files are updated to the same new version.

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths (relative to repo root)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYPROJECT_FILES=(
    "${REPO_ROOT}/apps/tg-jenkins-bot/pyproject.toml"
    "${REPO_ROOT}/apps/config-ui/pyproject.toml"
    "${REPO_ROOT}/apps/agent-control/pyproject.toml"
)

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
die() { echo -e "${RED}error:${RESET} $*" >&2; exit 1; }
info() { echo -e "${CYAN}info:${RESET} $*"; }
ok() { echo -e "${GREEN}ok:${RESET} $*"; }
warn() { echo -e "${YELLOW}warn:${RESET} $*"; }

require_cmd() { command -v "$1" &>/dev/null || die "'$1' is required but not found in PATH."; }

# Validate semver format (digits only, no pre-release suffix)
is_semver() { [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; }

# Compare two semver strings: returns 0 if $1 > $2
semver_gt() {
    local a_str="$1" b_str="$2"
    local -a a b
    IFS='.' read -ra a <<< "$a_str"
    IFS='.' read -ra b <<< "$b_str"
    for i in 0 1 2; do
        if (( ${a[$i]:-0} > ${b[$i]:-0} )); then return 0; fi
        if (( ${a[$i]:-0} < ${b[$i]:-0} )); then return 1; fi
    done
    return 1  # equal is not greater
}

# Bump a semver string: bump patch|minor|major
bump_version() {
    local version="$1" part="$2"
    local -a parts
    IFS='.' read -ra parts <<< "$version"
    local major=${parts[0]:-0} minor=${parts[1]:-0} patch=${parts[2]:-0}
    case "$part" in
        major) echo "$((major + 1)).0.0" ;;
        minor) echo "${major}.$((minor + 1)).0" ;;
        patch) echo "${major}.${minor}.$((patch + 1))" ;;
        *)     die "Unknown bump type: '$part'. Use patch, minor, or major." ;;
    esac
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
DRY_RUN=false
BUMP_ARG=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        -*) die "Unknown flag: '$arg'" ;;
        *) BUMP_ARG="$arg" ;;
    esac
done

[[ -n "$BUMP_ARG" ]] || die "Missing argument. Usage: version.sh <patch|minor|major|x.y.z> [--dry-run]"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
require_cmd git
require_cmd sed

cd "${REPO_ROOT}"

# Must be inside a git repo
git rev-parse --git-dir &>/dev/null || die "Not a git repository."

# Working tree must be clean (untracked files are OK)
if [[ -n "$(git status --porcelain -- '*.toml' '*.py' '*.yml' '*.yaml' 2>/dev/null)" ]]; then
    warn "Working tree has uncommitted changes. It is recommended to start from a clean state."
    echo ""
    git status --short
    echo ""
    read -r -p "Continue anyway? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || { info "Aborted."; exit 0; }
fi

# ---------------------------------------------------------------------------
# Determine current and new versions
# ---------------------------------------------------------------------------
# Source of truth: latest git tag. Fall back to 0.0.0 if no tags exist yet.
CURRENT_TAG="$(git tag --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1 || true)"

if [[ -z "$CURRENT_TAG" ]]; then
    CURRENT_VERSION="0.0.0"
    warn "No version tags found. Treating current version as 0.0.0."
else
    CURRENT_VERSION="${CURRENT_TAG#v}"
    info "Current version: ${BOLD}${CURRENT_TAG}${RESET}"
fi

# Compute new version
if is_semver "$BUMP_ARG"; then
    # Explicit version provided
    NEW_VERSION="$BUMP_ARG"
else
    # Bump type provided
    NEW_VERSION="$(bump_version "$CURRENT_VERSION" "$BUMP_ARG")"
fi

is_semver "$NEW_VERSION" || die "Invalid version: '$NEW_VERSION'. Must be x.y.z."

semver_gt "$NEW_VERSION" "$CURRENT_VERSION" \
    || die "New version ${NEW_VERSION} must be greater than current ${CURRENT_VERSION}."

NEW_TAG="v${NEW_VERSION}"

# ---------------------------------------------------------------------------
# Preview changes
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Version bump:${RESET} ${CURRENT_VERSION} → ${BOLD}${NEW_VERSION}${RESET}"
echo ""
echo "Files to update:"
for f in "${PYPROJECT_FILES[@]}"; do
    rel="${f#${REPO_ROOT}/}"
    echo "  • ${rel}"
done
echo ""
echo "Git actions:"
echo "  git commit -m \"chore: bump version to ${NEW_TAG}\""
echo "  git tag ${NEW_TAG}"
echo "  git push && git push origin ${NEW_TAG}"
echo ""

if $DRY_RUN; then
    warn "Dry run — no changes made."
    exit 0
fi

read -r -p "Proceed? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { info "Aborted."; exit 0; }
echo ""

# ---------------------------------------------------------------------------
# Update pyproject.toml files
# ---------------------------------------------------------------------------
for f in "${PYPROJECT_FILES[@]}"; do
    # Replace the version line in [project] section
    # Matches: version = "x.y.z"  (with any surrounding whitespace)
    sed -i.bak "s/^version = \"[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\"/version = \"${NEW_VERSION}\"/" "$f"
    rm -f "${f}.bak"
    ok "Updated ${f#${REPO_ROOT}/}"
done

# ---------------------------------------------------------------------------
# Git commit, tag, push
# ---------------------------------------------------------------------------
git add "${PYPROJECT_FILES[@]}"
git commit -m "chore: bump version to ${NEW_TAG}"
ok "Committed"

git tag "${NEW_TAG}"
ok "Tagged ${NEW_TAG}"

git push
git push origin "${NEW_TAG}"
ok "Pushed — GitHub Actions build triggered for ${NEW_TAG}"

echo ""
echo -e "${GREEN}${BOLD}Done!${RESET} Watch the build at:"
echo "  https://github.com/$(git remote get-url origin | sed 's|.*github.com[/:]||;s|\.git$||')/actions"
