#!/usr/bin/env bash
# Runs the release APK on a booted emulator the way a Play reviewer meets it:
# the pairing screen, then every place on sample data. It fails on a crash —
# the process gone, or a FATAL EXCEPTION in logcat, which is how R8 shrinking
# a plugin's classes shows up — and leaves a screenshot of each in $out for a
# person to look at (edge to edge, the server named on pairing).
#
# Each place is a cold start with the launch route the app reads for sample
# data (`--es route /sample/flow`): adb can't reliably tap Flutter's widgets.
#
#   smoke-test.sh path/to/app-release.apk [out-dir]
set -euo pipefail
trap 'echo "::error::smoke-test.sh line $LINENO failed: $BASH_COMMAND"' ERR

apk=${1:?usage: smoke-test.sh app-release.apk [out-dir]}
out=${2:-smoke}
pkg=space.elghareeb.beats
mkdir -p "$out"

# A slow emulator's own apps (the launcher, System UI) raise "isn't
# responding" over everything; wait them out rather than photograph them.
dismiss_anr() {
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1 || return 0
  adb pull /sdcard/ui.xml "$out/ui.xml" >/dev/null 2>&1 || return 0
  xy=$(python3 - "$out/ui.xml" <<'EOF'
import re, sys
xml = open(sys.argv[1]).read()
if "isn't responding" in xml or "isn&apos;t responding" in xml:
    for node in re.findall(r'<node [^>]*>', xml):
        if 'text="Wait"' in node:
            x1, y1, x2, y2 = map(int, re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node).groups())
            print((x1 + x2) // 2, (y1 + y2) // 2)
            break
EOF
)
  if [ -n "$xy" ]; then
    adb shell input tap $xy
    echo "  (dismissed a system \"isn't responding\" dialog)"
    sleep 2
  fi
}

shot() { dismiss_anr; adb exec-out screencap -p > "$out/$1.png"; echo "  $1.png"; }

alive() {
  if ! adb shell pidof "$pkg" >/dev/null; then
    echo "::error::$pkg is not running after: $1"
    adb logcat -d > "$out/logcat.txt" || true
    grep -A 20 "FATAL EXCEPTION" "$out/logcat.txt" | head -40 || true
    exit 1
  fi
}

echo "Settling"
sleep 20
dismiss_anr

echo "Installing"
adb install -r "$apk" >/dev/null
adb logcat -c

# The launcher activity as Android resolves it: the Kotlin namespace
# (com.beats.beats_companion) isn't the application id.
activity=$(adb shell cmd package resolve-activity --brief -c android.intent.category.LAUNCHER "$pkg" | tr -d '\r' | tail -1)
echo "Launching $activity"

open() {
  adb shell am force-stop "$pkg"
  if [ -n "$1" ]; then
    adb shell am start -W -n "$activity" --es route "$1" >/dev/null
  else
    adb shell am start -W -n "$activity" >/dev/null
  fi
  sleep 12
  alive "opening ${1:-the app}"
}

open ""
shot 1-pairing

for place in today flow coach body find focus; do
  open "/sample/$place"
  shot "2-$place"
done

adb logcat -d > "$out/logcat.txt"
if grep -q "FATAL EXCEPTION" "$out/logcat.txt"; then
  echo "::error::a FATAL EXCEPTION is in logcat"
  grep -A 20 "FATAL EXCEPTION" "$out/logcat.txt" | head -40
  exit 1
fi
echo "No crash."
