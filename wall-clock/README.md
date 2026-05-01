# Beats Wall Clock

ESP32 firmware for the Beats wall-mounted timer device. Three buttons (start/stop, next-project, mode), a 2.9" e-ink display, a 7-LED WS2812B strip, and a Wi-Fi connection to the API at `http://<host>:7999`.

## Hardware

- ESP32 dev board (any flavor; `board = esp32dev` in `platformio.ini`)
- Waveshare 2.9" B/W e-ink (296×128, GxEPD2_290_T94_V2 driver)
- 7× WS2812B / NeoPixel
- 3× momentary tactile buttons (active-low, internal pullup)
- (Optional) battery + voltage divider on `BATTERY_PIN`, USB-detect on `USB_DETECT_PIN`

Pin assignments live in [`src/config.h`](src/config.h).

## Building

```bash
cd wall-clock
# Edit src/config.h with your Wi-Fi credentials and a paired device JWT (see below)
pio run                      # build only
pio run --target upload      # build + flash over USB
pio device monitor           # 115200 baud
```

## Wi-Fi + auth setup

`src/config.h` ships with placeholder values that **you must edit locally before flashing**. Treat the file like an `.env` — never commit your filled-in version.

```c
#define WIFI_SSID      "your-network"
#define WIFI_PASSWORD  "your-passphrase"
#define API_BASE_URL   "http://192.168.1.42:7999"   // your beats API host
#define API_TOKEN      "tok_..."                    // device JWT, see below
```

To mint a device JWT, the wall-clock follows the same pairing flow as the daemon:

1. Open the web UI's Settings → Devices page and generate a pairing code.
2. POST it to `/api/device/pair/exchange` with curl:
   ```bash
   curl -X POST http://<host>:7999/api/device/pair/exchange \
       -H 'Content-Type: application/json' \
       -d '{"code":"<6-char-code>","device_name":"wall-clock"}'
   ```
3. Paste the returned `device_token` into `API_TOKEN` in `config.h`.

The token persists across firmware flashes (it lives in source, not NVS). To rotate, regenerate from the Settings page and re-flash.

## Once it's running

- The clock connects to Wi-Fi, configures NTP via `pool.ntp.org`, then fetches today's status from `/api/device/status` every 10 seconds.
- The mode button cycles `ACTIVE_TIMER` → `CLOCK` → `IDLE_SUMMARY` → `WEEKLY_PROGRESS` and back.
- `WEEKLY_PROGRESS` fetches the last 7 days of tracked minutes from `/api/device/weekly` on first entry and refreshes every 5 minutes while the mode is active. Other modes don't pull this — radio is the dominant power draw.
- A long-press on the mode button toggles a 25/5 Pomodoro.
- USB-powered + idle + no-pomodoro auto-switches to the dock view.
- Failed timer start/stop (any non-2xx, WiFi blip, etc.) flashes the LED strip red 3× so a rejected button press doesn't appear to vanish — the next forced status poll repaints from truth right after.
- Heartbeats to `/api/device/heartbeat` carry battery voltage, WiFi RSSI, and uptime so the API can show "device last seen" + low-battery state in the Settings UI.

If Wi-Fi drops mid-session the firmware auto-reconnects (`WiFi.setAutoReconnect(true)` in `setup()`), so you don't need to power-cycle.

## Limitations

- The clock currently talks plain HTTP. Pointing `API_BASE_URL` at an `https://` host won't work — the firmware uses `HTTPClient::begin(url)` rather than the secure-client variant.
- The display's e-ink refresh is full-redraw, not partial — every mode switch ghosts briefly. A partial-update mode is the obvious next firmware delta but blocked on a GxEPD2 driver upgrade.

## Layout

```
src/
├── main.cpp          Setup + main loop + button dispatch
├── config.h          Wi-Fi creds + API host + pin assignments  ← local edits only
├── api_client.{h,cpp}  GET /status, POST /start, /stop, /heartbeat
├── eink_display.{h,cpp} GxEPD2 wrappers for clock / timer / dock / weekly views
├── led_strip.{h,cpp} FastLED helpers (energy meter, progress bar, pulse)
├── button.{h,cpp}    Debounced single/double/long-press detection
└── pomodoro.{h,cpp}  25/5 work/break state machine
```
