#!/bin/zsh
# Renders the Google Play listing's images into android/en-US/images/:
#
#   icon.png             512×512, the full-bleed mark (Play rounds it itself)
#   featureGraphic.png   1024×500, from feature-graphic.html
#   phoneScreenshots/    1080×1920, the app on sample data
#
#   companion/store/render.sh              # everything
#   companion/store/render.sh screenshots  # one of: icon, graphic, screenshots
#
# Needs rsvg-convert (brew install librsvg) and Google Chrome. Screenshots
# run the Mac debug build at phone size on sample data (LIFEPETE_PHONE=store,
# LIFEPETE_SAMPLE=quiet), so they never show a real account; they need an
# unlocked screen, since macOS captures nothing while it is locked.
set -euo pipefail

here=${0:A:h}
companion=${here:h}
images=$here/android/en-US/images
chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
what=${1:-all}

mkdir -p $images/phoneScreenshots

if [[ $what == all || $what == icon ]]; then
  rsvg-convert -w 512 -h 512 -o $images/icon.png $companion/../shared/brand/maskable.svg
  echo "icon.png"
fi

if [[ $what == all || $what == graphic ]]; then
  "$chrome" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --window-size=1024,500 --virtual-time-budget=8000 \
    --screenshot=$images/featureGraphic.png "file://$here/feature-graphic.html" 2>/dev/null
  echo "featureGraphic.png"
fi

if [[ $what == all || $what == screenshots ]]; then
  app=$companion/build/macos/Build/Products/Debug/beats_companion.app
  (cd $companion && flutter build macos --debug >/dev/null)
  # The window's id, from CoreGraphics: screencapture -l wants it.
  window_id() {
    swift -e 'import CoreGraphics
      let all = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as! [[String: Any]]
      for w in all where (w["kCGWindowOwnerName"] as? String) == "LifePete" {
        let b = w["kCGWindowBounds"] as! [String: Any]
        if (b["Width"] as! Double) == 540 { print(w["kCGWindowNumber"]!); break }
      }'
  }
  for shot in "1-today LIFEPETE_SECTION=today" "2-start LIFEPETE_ROUTE=find" "3-flow LIFEPETE_SECTION=flow" \
              "4-coach LIFEPETE_SECTION=coach" "5-body LIFEPETE_SECTION=body" "6-focus LIFEPETE_ROUTE=focus"; do
    name=${shot%% *}; env=${shot#* }
    pkill -f "Debug/beats_companion.app/Contents/MacOS" || true
    sleep 1
    open -n --env LIFEPETE_PHONE=store --env LIFEPETE_SAMPLE=quiet --env $env $app
    sleep 10
    screencapture -x -o -l "$(window_id)" $images/phoneScreenshots/$name.png
    echo "phoneScreenshots/$name.png"
  done
  pkill -f "Debug/beats_companion.app/Contents/MacOS" || true
fi
