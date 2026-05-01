#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <FastLED.h>

// DeviceStatus mirrors GET /api/device/status. Field names stay
// firmware-idiomatic (is_active vs the API's clocked_in,
// today_minutes vs daily_total_minutes); the parser in
// api_client.cpp does the renaming. Colors are pre-parsed to
// CRGB so main.cpp can pass them straight to LedStrip without
// a hexToRgb step — the API now returns three-int RGB lists,
// not hex strings.
struct DeviceStatus {
    bool is_active;
    String project_id;
    String project_name;
    CRGB project_color;
    int elapsed_minutes;
    int today_minutes;
    int energy_leds;  // 0-7
    CRGB theme_accent;
};

struct FavoriteProject {
    String id;
    String name;
    CRGB color;
};

class ApiClient {
public:
    ApiClient(const char* baseUrl, const char* token);

    bool getStatus(DeviceStatus& status);
    bool startTimer(const String& projectId);
    bool stopTimer();
    bool getFavorites(FavoriteProject* projects, int& count, int maxCount = 9);
    bool postHeartbeat();
    bool getDashboard(DeviceStatus& status, String& nextEvent, int& goalPct);

private:
    String _baseUrl;
    String _token;

    bool httpGet(const String& path, JsonDocument& doc);
    bool httpPost(const String& path, const String& body = "{}");
};
