#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>

struct DeviceStatus {
    bool is_active;
    String project_id;
    String project_name;
    String project_color;  // hex e.g. "#5B9CF6"
    int elapsed_seconds;
    int today_minutes;
    int energy_leds;  // 0-7
    String theme_accent;
};

struct FavoriteProject {
    String id;
    String name;
    String color;
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
