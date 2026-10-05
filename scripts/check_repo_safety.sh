#!/usr/bin/env bash
# Public-repository safety guard.
#
# Fails if files that are about to be (or already are) tracked include:
#   - files larger than MAX_BYTES (default 5 MB)
#   - private/reference-material path patterns (archives, HEIC photos, private specs)
#   - real-looking .env files (only .env.example is allowed)
#   - content patterns that indicate private material, private keys, or local absolute paths
#
# Usage:
#   scripts/check_repo_safety.sh            # check all tracked files (CI)
#   scripts/check_repo_safety.sh --staged   # check staged files (pre-commit hook)
#   scripts/check_repo_safety.sh --all      # everything that would be committed (or, before
#                                           # `git init`, every file in the tree)
#
# Secret scanning proper is done by gitleaks (CI + optional local hook); this script
# covers what gitleaks does not: size, reference-material paths, and private-content markers.
set -euo pipefail

MAX_BYTES="${MAX_BYTES:-5242880}"
mode="${1:---tracked}"
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

list_files() {
  case "$mode" in
    --staged)  git diff --cached --name-only --diff-filter=ACMR ;;
    --tracked) git ls-files ;;
    --all)     # Everything that would be committed: tracked + untracked-but-not-ignored.
               # Before `git init`, fall back to every file in the tree.
               if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
                 git ls-files --cached --others --exclude-standard
                 return
               fi
               find . -type f \
                  -not -path './.git/*' -not -path '*/node_modules/*' -not -path '*/.venv/*' \
                  -not -path '*/.next/*' -not -path '*/.cache/*' -not -path '*/__pycache__/*' \
                  -not -path '*/.mypy_cache/*' -not -path '*/.ruff_cache/*' -not -path '*/.pytest_cache/*' \
                  | sed 's|^\./||' ;;
    *) echo "unknown mode: $mode" >&2; exit 2 ;;
  esac
}

# Path patterns (Perl regex, case-insensitive) that must never be committed.
forbidden_paths='(\.zip|\.heic|\.tar|\.tgz|\.tar\.gz|\.7z|\.rar|\.dmg)$|(^|/)(private|confidential|reference_material)/|-private/|\.local$|(^|/)\.env$|(^|/)\.env\.(?!example$)'

# Content patterns (extended regex) that indicate private material or local leakage.
# Kept deliberately generic: this file is public.
forbidden_content='Internal[^A-Za-z0-9]{1,6}Confidential|INTERNAL USE ONLY|BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY|/Users/[A-Za-z0-9._-]+/|/private/tmp/|/home/runner/work/'

# Optional untracked deny-list (one Perl regex per line, '#' comments) for machine-specific
# private names that must not be published even as patterns.
denylist_file="$root/scripts/safety-denylist.local"
if [ -f "$denylist_file" ]; then
  extra="$(grep -vE '^\s*(#|$)' "$denylist_file" | paste -sd'|' -)"
  if [ -n "$extra" ]; then
    forbidden_paths="$forbidden_paths|$extra"
    forbidden_content="$forbidden_content|$extra"
  fi
fi

# Files allowed to contain the content patterns above (this script documents them).
content_allowlist='^scripts/check_repo_safety\.sh$'

fail=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  [ -f "$f" ] || continue

  if perl -e 'exit(($ARGV[0] =~ /$ARGV[1]/i) ? 0 : 1)' "$f" "$forbidden_paths"; then
    echo "FORBIDDEN PATH: $f"; fail=1; continue
  fi

  size=$(wc -c <"$f" | tr -d ' ')
  if [ "$size" -gt "$MAX_BYTES" ]; then
    echo "TOO LARGE ($size bytes > $MAX_BYTES): $f"; fail=1
  fi

  if ! printf '%s\n' "$f" | grep -qE "$content_allowlist"; then
    if LC_ALL=C grep -IqE "$forbidden_content" "$f" 2>/dev/null; then
      echo "FORBIDDEN CONTENT: $f"
      LC_ALL=C grep -InE "$forbidden_content" "$f" | head -3 | sed 's/^/    /'
      fail=1
    fi
  fi
done < <(list_files)

if [ "$fail" -ne 0 ]; then
  echo "repo safety check FAILED ($mode)" >&2
  exit 1
fi
echo "repo safety check passed ($mode)"
