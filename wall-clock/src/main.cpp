/**
 * Beats Wall Clock — ESP32 Firmware
 *
 * Features:
 * - WiFi connection to Beats API
 * - 3-button interaction (start/stop, next project, mode)
 * - WS2812B LED strip (energy meter, progress bar, ambient color)
 * - 2.9" Waveshare e-ink display
 * - Pomodoro mode (long-press Mode button)
 * - Charging dock display mode
 */

#include <WiFi.h>
#include "api_client.h"
#include "button.h"
#include "config.h"
#include "eink_display.h"
#include "led_strip.h"
#include "pomodoro.h"

// ============================================================================
// Globals
// ============================================================================

ApiClient api(API_BASE_URL, API_TOKEN);
LedStrip leds;
EinkDisplay eink;
Pomodoro pomodoro;

Button btnStartStop(BTN_START_STOP);
Button btnNextProject(BTN_NEXT_PROJECT);
Button btnMode(BTN_MODE);

DeviceStatus status;
FavoriteProject favorites[9];
int favoriteCount = 0;
int currentFavoriteIndex = 0;

DisplayMode displayMode = DisplayMode::ACTIVE_TIMER;

unsigned long lastStatusPoll = 0;
unsigned long lastEinkRefresh = 0;
unsigned long lastHeartbeat = 0;

// ============================================================================
// Helpers
// ============================================================================

float readBatteryVoltage() {
    int raw = analogRead(BATTERY_PIN);
    // ESP32 ADC: 0-4095, with voltage divider mapping 4.2V -> ~2500
    return (raw / 4095.0f) * 3.3f * 2.0f;  // *2 for voltage divider
}

int readBatteryPercent() {
    float voltage = readBatteryVoltage();
    return constrain((int)((voltage - 3.0f) / 1.2f * 100), 0, 100);
}

bool isUsbPowered() {
    return digitalRead(USB_DETECT_PIN) == HIGH;
}

// ============================================================================
// Setup
// ============================================================================

void setup() {
    Serial.begin(115200);
    Serial.println("Beats Wall Clock starting...");

    // Pin modes
    pinMode(BATTERY_PIN, INPUT);
    pinMode(USB_DETECT_PIN, INPUT);

    // Initialize hardware
    leds.begin();
    eink.begin();
    btnStartStop.begin();
    btnNextProject.begin();
    btnMode.begin();

    // WiFi. setAutoReconnect+persistent reset to true after every
    // begin() — calling them explicitly is harmless and documents
    // the intent. Without auto-reconnect, the wall-clock connects
    // once at boot and goes silent for the rest of its life if the
    // AP blips: a failure mode for a device that's literally mounted
    // on a wall and never gets power-cycled.
    WiFi.setAutoReconnect(true);
    WiFi.persistent(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    eink.showStatusLine("Connecting WiFi...");

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected: " + WiFi.localIP().toString());
        eink.showStatusLine("Connected");

        // Configure time via NTP
        configTime(0, 0, "pool.ntp.org");

        // Initial data fetch
        api.getStatus(status);
        api.getFavorites(favorites, favoriteCount);
    } else {
        Serial.println("\nWiFi connection failed");
        eink.showStatusLine("WiFi failed — offline mode");
    }

    // Initial display
    if (status.is_active) {
        leds.setActiveColor(status.project_color);
        eink.showActiveTimer(status.project_name, status.elapsed_minutes * 60,
                             status.today_minutes, 0);
    } else {
        leds.showEnergyMeter(status.energy_leds, status.theme_accent);
        eink.showIdleSummary(status.today_minutes, 0, 0);
    }
}

// ============================================================================
// Main Loop
// ============================================================================

void loop() {
    unsigned long now = millis();

    // ----- Button handling -----

    ButtonEvent startStopEvent = btnStartStop.update();
    ButtonEvent nextEvent = btnNextProject.update();
    ButtonEvent modeEvent = btnMode.update();

    // Start/Stop button
    if (startStopEvent == ButtonEvent::SINGLE_PRESS) {
        if (pomodoro.state() != PomodoroState::INACTIVE) {
            // In pomodoro mode — ignore
        } else if (status.is_active) {
            if (api.stopTimer()) {
                Serial.println("Timer stopped");
                leds.fadeToBlack();
            } else {
                // Server didn't accept the stop — give the user a visible
                // signal so the press doesn't appear to vanish. The next
                // forced status poll repaints from truth.
                Serial.println("Timer stop failed");
                leds.flashError();
            }
        } else if (favoriteCount > 0) {
            String projectId = favorites[currentFavoriteIndex].id;
            if (api.startTimer(projectId)) {
                Serial.println("Timer started for " + favorites[currentFavoriteIndex].name);
                leds.setActiveColor(favorites[currentFavoriteIndex].color);
            } else {
                Serial.println("Timer start failed");
                leds.flashError();
            }
        }
        // Force immediate status refresh
        lastStatusPoll = 0;
    }

    // Next Project button — cycle favorites
    if (nextEvent == ButtonEvent::SINGLE_PRESS && !status.is_active) {
        if (favoriteCount > 0) {
            currentFavoriteIndex = (currentFavoriteIndex + 1) % favoriteCount;
            String name = favorites[currentFavoriteIndex].name;
            CRGB color = favorites[currentFavoriteIndex].color;
            leds.setColor(color);
            eink.showStatusLine(name);
            Serial.println("Selected: " + name);
        }
    }

    // Double-press start/stop — also cycle favorites (legacy v1 polish behavior)
    if (startStopEvent == ButtonEvent::DOUBLE_PRESS && !status.is_active) {
        if (favoriteCount > 0) {
            currentFavoriteIndex = (currentFavoriteIndex + 1) % favoriteCount;
            eink.showStatusLine(favorites[currentFavoriteIndex].name);
        }
    }

    // Mode button — cycle display modes
    if (modeEvent == ButtonEvent::SINGLE_PRESS) {
        if (pomodoro.state() != PomodoroState::INACTIVE) {
            pomodoro.stop();
            displayMode = DisplayMode::ACTIVE_TIMER;
        } else {
            switch (displayMode) {
                case DisplayMode::ACTIVE_TIMER:
                    displayMode = DisplayMode::CLOCK;
                    break;
                case DisplayMode::CLOCK:
                    displayMode = DisplayMode::IDLE_SUMMARY;
                    break;
                case DisplayMode::IDLE_SUMMARY:
                    displayMode = DisplayMode::WEEKLY_PROGRESS;
                    break;
                default:
                    displayMode = DisplayMode::ACTIVE_TIMER;
                    break;
            }
        }
        lastEinkRefresh = 0;  // Force refresh
    }

    // Long-press Mode — enter/exit Pomodoro
    if (modeEvent == ButtonEvent::LONG_PRESS) {
        if (pomodoro.state() == PomodoroState::INACTIVE) {
            pomodoro.start();
            displayMode = DisplayMode::POMODORO;
            Serial.println("Pomodoro started");
        } else {
            pomodoro.stop();
            displayMode = DisplayMode::ACTIVE_TIMER;
            Serial.println("Pomodoro cancelled");
        }
        lastEinkRefresh = 0;
    }

    // ----- Pomodoro update -----
    if (pomodoro.update()) {
        // State changed (work -> break or break -> work)
        lastEinkRefresh = 0;
    }

    // ----- Charging dock mode -----
    if (isUsbPowered() && !status.is_active && pomodoro.state() == PomodoroState::INACTIVE) {
        displayMode = DisplayMode::DOCK;
    }

    // ----- API polling -----
    if (now - lastStatusPoll >= STATUS_POLL_INTERVAL_MS) {
        lastStatusPoll = now;
        DeviceStatus newStatus;
        if (api.getStatus(newStatus)) {
            bool wasActive = status.is_active;
            status = newStatus;

            // Update LEDs based on state
            if (status.is_active) {
                leds.setActiveColor(status.project_color);
            } else if (wasActive) {
                // Just stopped — fade out
                leds.fadeToBlack();
            } else {
                // Idle — ambient energy meter
                leds.showEnergyMeter(status.energy_leds, status.theme_accent);
            }
        }
    }

    // ----- Heartbeat -----
    if (now - lastHeartbeat >= HEARTBEAT_INTERVAL_MS) {
        lastHeartbeat = now;
        // Send real telemetry so /api/device/heartbeat surfaces
        // battery / signal / uptime to the dashboard. Earlier
        // firmware sent an empty body, which made the heartbeat
        // a pure last-seen ping with no diagnostic value.
        api.postHeartbeat(readBatteryVoltage(), WiFi.RSSI(), (long)(now / 1000));
    }

    // ----- E-ink refresh -----
    unsigned long refreshInterval = (pomodoro.state() != PomodoroState::INACTIVE)
        ? 1000  // Update pomodoro countdown every second
        : EINK_REFRESH_INTERVAL_MS;

    if (now - lastEinkRefresh >= refreshInterval) {
        lastEinkRefresh = now;

        switch (displayMode) {
            case DisplayMode::ACTIVE_TIMER:
                if (status.is_active) {
                    eink.showActiveTimer(status.project_name, status.elapsed_seconds,
                                         status.today_minutes, 0);
                } else {
                    eink.showIdleSummary(status.today_minutes, 0, 0);
                }
                break;

            case DisplayMode::CLOCK:
                eink.showClock(status.today_minutes);
                break;

            case DisplayMode::IDLE_SUMMARY:
                eink.showIdleSummary(status.today_minutes, 0, 0);
                break;

            case DisplayMode::WEEKLY_PROGRESS: {
                int dayMins[7] = {0};  // TODO: fetch from API
                eink.showWeeklyProgress(dayMins);
                break;
            }

            case DisplayMode::POMODORO:
                eink.showPomodoro(pomodoro.remainingSeconds(), pomodoro.isBreak());
                leds.pulseAnimation(status.theme_accent, now);
                break;

            case DisplayMode::DOCK:
                eink.showDock(status.today_minutes, readBatteryPercent());
                break;
        }
    }

    // Ambient LED pulse when idle (not in active timer or pomodoro)
    if (!status.is_active && pomodoro.state() == PomodoroState::INACTIVE) {
        // Gentle idle pulse every few seconds
        static unsigned long lastPulse = 0;
        if (now - lastPulse >= 50) {
            lastPulse = now;
            if (status.energy_leds > 0) {
                // Keep energy meter, slight pulse
            }
        }
    }

    delay(10);  // Small delay to prevent tight-looping
}
