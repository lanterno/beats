#pragma once

// ============================================================================
// WiFi Configuration
// ============================================================================
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// ============================================================================
// Beats API Configuration
// ============================================================================
#define API_BASE_URL "http://YOUR_API_HOST:7999"
#define API_TOKEN "YOUR_JWT_TOKEN"

// ============================================================================
// Hardware Pin Configuration
// ============================================================================

// LED strip (WS2812B / NeoPixel)
#define LED_PIN 13
#define NUM_LEDS 7

// Buttons
#define BTN_START_STOP 25  // Main button: start/stop timer
#define BTN_NEXT_PROJECT 26  // Cycle through favorite projects
#define BTN_MODE 27  // Toggle display mode

// E-ink display (Waveshare 2.9" SPI)
#define EINK_CS 5
#define EINK_DC 17
#define EINK_RST 16
#define EINK_BUSY 4

// Battery voltage sensing
#define BATTERY_PIN 34  // ADC pin for voltage divider
#define USB_DETECT_PIN 35  // High when USB power connected

// ============================================================================
// Timing Configuration
// ============================================================================
#define STATUS_POLL_INTERVAL_MS 10000  // Poll API every 10 seconds
#define EINK_REFRESH_INTERVAL_MS 60000  // Refresh e-ink every 60 seconds
#define HEARTBEAT_INTERVAL_MS 300000  // Send heartbeat every 5 minutes
#define DEBOUNCE_MS 50
#define DOUBLE_PRESS_WINDOW_MS 400
#define LONG_PRESS_MS 1000

// ============================================================================
// Pomodoro Configuration
// ============================================================================
#define POMODORO_WORK_MS (25 * 60 * 1000)
#define POMODORO_BREAK_MS (5 * 60 * 1000)
