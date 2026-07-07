#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# install-apk.sh — Robust APK installer via adb
# Usage: install-apk.sh <path-to-apk>
# ──────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

fail() {
  echo -e "${RED}[ERROR]${NC} $*" >&2
  exit 1
}

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }

# ── Argument check ────────────────────────────
[[ $# -lt 1 ]] && fail "Usage: $0 <path-to-apk>"
APK_PATH="$1"

# ── File existence check ─────────────────────
[[ -f "$APK_PATH" ]] || fail "APK file not found: $APK_PATH"
[[ -s "$APK_PATH" ]] || fail "APK file is empty: $APK_PATH"

# ── adb availability ─────────────────────────
command -v adb &>/dev/null || fail "adb not found in PATH"

# ── adb device check ─────────────────────────
DEVICES=$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1}')
[[ -n "$DEVICES" ]] || fail "No Android device connected. Run 'adb devices' to check."

info "Using device(s):"
echo "$DEVICES" | sed 's/^/  /'

# More than one device → warn but proceed (operates on first)
if [[ $(echo "$DEVICES" | wc -l) -gt 1 ]]; then
  warn "Multiple devices detected — installing on the first one listed"
fi

# ── Resolve the APK path ─────────────────────
# Convert relative to absolute so adb push gets the right file
APK_PATH="$(cd "$(dirname "$APK_PATH")" && pwd -P)/$(basename "$APK_PATH")"

# ── Generate a unique remote name to avoid collisions ──
REMOTE_NAME="install-$(basename "$APK_PATH" 2>/dev/null || echo 'tmp.apk')"

# ── Clean up any leftover from a previous crashed run ──
adb shell "rm -f \"/sdcard/${REMOTE_NAME}\"" 2>/dev/null || true

# ── Push ──────────────────────────────────────
info "Pushing APK to device…"
adb push "$APK_PATH" "/sdcard/${REMOTE_NAME}" || fail "adb push failed"

# ── Install ───────────────────────────────────
info "Installing…"
INSTALL_OUT=$(adb shell "CLASSPATH=/system/framework/pm.jar app_process /system/bin \
  com.android.commands.pm.Pm install -r \"/sdcard/${REMOTE_NAME}\"" 2>&1)

# Check for known failure indicators in the output
if echo "$INSTALL_OUT" | grep -qiE '(failure|error|not installed|cannot install)'; then
  warn "Installation reported issues. Output:"
  echo "$INSTALL_OUT" | sed 's/^/  /'
  # Still attempt cleanup — do not exit yet
fi

# ── Clean up remote APK ──────────────────────
info "Cleaning up temporary file on device…"
adb shell "rm -f \"/sdcard/${REMOTE_NAME}\" && sync" || warn "Cleanup on device failed (non-fatal)"

# ── Dalvik-cache wipe ────────────────────────
info "Clearing dalvik-cache…"
# These paths may not exist on all devices; suppress errors
adb shell 'for d in /data/dalvik-cache/arm /data/dalvik-cache/arm64; do
  if [ -d "$d" ]; then
    rm -rf "${d:?}"/* && echo "Cleared $d"
  fi
done && sync' || warn "Dalvik-cache cleanup failed (non-fatal)"

# ── Done ──────────────────────────────────────
if echo "$INSTALL_OUT" | grep -qiE '(failure|error)'; then
  fail "Installation appears to have failed. See output above."
fi

info "Installation completed successfully!"
