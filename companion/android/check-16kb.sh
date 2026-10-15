#!/usr/bin/env bash
# Fails when a native library in an Android App Bundle is not aligned to
# 16 KB pages. Google Play refuses new apps and updates targeting Android 15+
# whose 64-bit libraries are 4 KB-aligned, and the usual culprit is a
# plugin's prebuilt .so (ML Kit behind mobile_scanner, say), not our code.
#
#   check-16kb.sh build/app/outputs/bundle/release/app-release.aab
set -euo pipefail

bundle=${1:?usage: check-16kb.sh path/to/app.aab}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
unzip -q "$bundle" 'base/lib/*' -d "$work" 2>/dev/null || true

checked=0
fail=0
for so in "$work"/base/lib/arm64-v8a/*.so "$work"/base/lib/x86_64/*.so; do
  [ -e "$so" ] || continue
  checked=$((checked + 1))
  for align in $(readelf -lW "$so" | awk '$1 == "LOAD" { print $NF }'); do
    if [ $((align)) -lt 16384 ]; then
      echo "::error::${so#"$work"/} has a LOAD segment aligned to $align, not 16 KB"
      fail=1
    fi
  done
done

echo "Checked $checked 64-bit native libraries."
exit $fail
