#!/usr/bin/env bash
# Runs the release APK on a booted emulator the way a Play reviewer would:
# open it, tap "Look around with sample data", and look at every place. It
# fails on a crash (the process gone, or a FATAL EXCEPTION in logcat — what
# R8 shrinking a plugin's classes looks like), and leaves a screenshot of
# each step in $OUT for a person to look at.
#
#   smoke-test.sh path/to/app-release.apk [out-dir]
set -euo pipefail
trap 'echo "::error::smoke-test.sh line $LINENO failed: $BASH_COMMAND"' ERR

apk=${1:?usage: smoke-test.sh app-release.apk [out-dir]}
out=${2:-smoke}
pkg=space.elghareeb.beats
mkdir -p "$out"

shot() { adb exec-out screencap -p > "$out/$1.png"; echo "  $1.png"; }

alive() {
  if ! adb shell pidof "$pkg" >/dev/null; then
    echo "::error::$pkg is not running after: $1"
    adb logcat -d -s AndroidRuntime:E flutter:V > "$out/logcat.txt" || true
    exit 1
  fi
}

# Taps the on-screen node whose text or description contains $1, found in a
# UI Automator dump (Flutter exposes its semantics to it).
tap() {
  for _ in 1 2 3 4 5; do
    adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1 || true
    adb pull /sdcard/ui.xml "$out/ui.xml" >/dev/null 2>&1 || true
    xy=$(python3 - "$out/ui.xml" "$1" <<'EOF'
import re, sys
xml, want = open(sys.argv[1]).read(), sys.argv[2].lower()
for node in re.findall(r'<node [^>]*>', xml):
    label = ' '.join(re.findall(r'(?:text|content-desc)="([^"]*)"', node)).lower()
    if want in label:
        x1, y1, x2, y2 = map(int, re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node).groups())
        print((x1 + x2) // 2, (y1 + y2) // 2)
        break
EOF
)
    if [ -n "$xy" ]; then
      adb shell input tap $xy
      echo "  tapped \"$1\" at $xy"
      return
    fi
    sleep 3
  done
  echo "::error::nothing on screen reads \"$1\""
  exit 1
}

echo "Installing"
adb install -r "$apk" >/dev/null
adb logcat -c

echo "Launching"
# The launcher activity as Android resolves it: the Kotlin namespace
# (com.beats.beats_companion) isn't the application id, so ".MainActivity"
# would point at a class that doesn't exist.
activity=$(adb shell cmd package resolve-activity --brief -c android.intent.category.LAUNCHER "$pkg" | tr -d '\r' | tail -1)
echo "  $activity"
adb shell am start -W -n "$activity" >/dev/null
sleep 15
alive "launch"
shot 1-pairing

tap "look around with sample data"
sleep 12
alive "opening sample data"
shot 2-today

for place in Flow Coach Body; do
  tap "$place"
  sleep 6
  alive "opening $place"
  shot "3-$(echo "$place" | tr '[:upper:]' '[:lower:]')"
done

tap "Today"
sleep 3
tap "Start or switch"
sleep 4
alive "opening the start sheet"
shot 4-start-sheet

adb logcat -d > "$out/logcat.txt"
if grep -q "FATAL EXCEPTION" "$out/logcat.txt"; then
  echo "::error::a FATAL EXCEPTION is in logcat"
  grep -A 20 "FATAL EXCEPTION" "$out/logcat.txt" | head -40
  exit 1
fi
echo "No crash."
