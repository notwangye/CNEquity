#!/usr/bin/env bash
# Isolated CNEquity lake backup/restore with checksum verification.
# Does not share object keys with ashare-quant's legacy Baostock snapshot.
set -euo pipefail
umask 077

: "${CNE_LAKE_ROOT:?CNE_LAKE_ROOT must point to a persistent CNEquity lake}"
: "${CNE_R2_REMOTE:?CNE_R2_REMOTE must be an existing rclone S3 remote}"
: "${CNE_R2_BUCKET:?CNE_R2_BUCKET required}"
mode="${1:-}"
case "$mode" in backup|restore|verify) ;; *) echo "usage: $0 backup|restore|verify" >&2; exit 2;; esac
root="$(realpath -m "$CNE_LAKE_ROOT")"
case "$root" in /|/tmp|/home|/mnt|/var) echo "Unsafe lake root" >&2; exit 2;; esac
# Forbid reuse of the existing legacy archive keys. Prefix is explicit and fixed.
target="${CNE_R2_REMOTE%:}:${CNE_R2_BUCKET}/cnequity-v1"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT

if [[ "$mode" == backup ]]; then
  [[ -d "$root/curated" && -d "$root/meta" ]] || {
    echo "Not a completed CNEquity curated lake; refusing backup" >&2; exit 3;
  }
  # Running ingestion is unsafe to snapshot: caller must serialize writers.
  [[ "${CNE_WRITERS_STOPPED:-false}" == true ]] || {
    echo "Stop writers and explicitly set CNE_WRITERS_STOPPED=true" >&2; exit 3;
  }
  archive="lake-${GITHUB_RUN_ID:-manual}-${GITHUB_RUN_ATTEMPT:-1}.tar.gz"
  # Preserve symlinks only if the lake does not contain any. Do not dereference.
  if find "$root" -type l -print -quit | grep -q .; then
    echo "Lake contains symlinks; refusing non-hermetic snapshot" >&2
    exit 3
  fi
  tar -czf "$temp/$archive" -C "$root" .
  (cd "$temp" && sha256sum "$archive" > "$archive.sha256")
  # Generation-specific immutable keys prevent clobbering an older good backup.
  rclone copyto "$temp/$archive" "$target/$archive" --immutable
  rclone copyto "$temp/$archive.sha256" "$target/$archive.sha256" --immutable
  rclone copyto "$target/$archive" "$temp/roundtrip.tar.gz"
  cmp "$temp/$archive" "$temp/roundtrip.tar.gz"
  echo "CNE_SNAPSHOT_BACKED_UP_AND_VERIFIED $archive"
  exit 0
fi

: "${CNE_SNAPSHOT_ID:?CNE_SNAPSHOT_ID must be a lake-RUN-ATTEMPT.tar.gz name}"
[[ "$CNE_SNAPSHOT_ID" =~ ^lake-[a-zA-Z0-9_-]+-[0-9]+\.tar\.gz$ ]] || {
  echo "Invalid immutable snapshot identifier" >&2; exit 2;
}
rclone copyto "$target/$CNE_SNAPSHOT_ID" "$temp/$CNE_SNAPSHOT_ID"
rclone copyto "$target/$CNE_SNAPSHOT_ID.sha256" "$temp/$CNE_SNAPSHOT_ID.sha256"
(cd "$temp" && sha256sum -c "$CNE_SNAPSHOT_ID.sha256")

# Guard extraction against path traversal, symlinks, devices and hardlinks.
python - "$temp/$CNE_SNAPSHOT_ID" <<'PY'
import sys, tarfile
from pathlib import PurePosixPath
with tarfile.open(sys.argv[1], "r:gz") as archive:
    for item in archive:
        path = PurePosixPath(item.name)
        if item.name.startswith("/") or ".." in path.parts:
            raise SystemExit("Unsafe archive path")
        if not (item.isfile() or item.isdir()):
            raise SystemExit("Unsupported archive member")
PY
if [[ "$mode" == verify ]]; then
  echo "CNE_SNAPSHOT_REMOTE_HASH_AND_MEMBERS_VERIFIED $CNE_SNAPSHOT_ID"
  exit 0
fi
# Never merge a snapshot into existing data; only restore to an empty root.
if [[ -e "$root" ]] && [[ -n "$(ls -A "$root")" ]]; then
  echo "Restore destination must be empty; no existing data overwritten" >&2
  exit 3
fi
mkdir -p "$root"
tar -xzf "$temp/$CNE_SNAPSHOT_ID" -C "$root" --no-same-owner
echo "CNE_SNAPSHOT_RESTORED_HASH_VERIFIED $CNE_SNAPSHOT_ID"
echo "Run cne check against the restored lake before research."
