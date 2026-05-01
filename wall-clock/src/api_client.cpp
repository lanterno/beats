#include "api_client.h"
#include <HTTPClient.h>
#include <WiFi.h>

ApiClient::ApiClient(const char* baseUrl, const char* token)
    : _baseUrl(baseUrl), _token(token) {}

bool ApiClient::httpGet(const String& path, JsonDocument& doc) {
    if (WiFi.status() != WL_CONNECTED) return false;

    HTTPClient http;
    http.begin(_baseUrl + path);
    http.addHeader("Authorization", "Bearer " + _token);
    http.addHeader("Accept", "application/json");

    int code = http.GET();
    if (code != 200) {
        http.end();
        return false;
    }

    DeserializationError err = deserializeJson(doc, http.getString());
    http.end();
    return err == DeserializationError::Ok;
}

bool ApiClient::httpPost(const String& path, const String& body) {
    if (WiFi.status() != WL_CONNECTED) return false;

    HTTPClient http;
    http.begin(_baseUrl + path);
    http.addHeader("Authorization", "Bearer " + _token);
    http.addHeader("Content-Type", "application/json");

    int code = http.POST(body);
    http.end();
    return code >= 200 && code < 300;
}

bool ApiClient::getStatus(DeviceStatus& status) {
    JsonDocument doc;
    if (!httpGet("/api/device/status", doc)) return false;

    status.is_active = doc["is_active"] | false;
    status.project_id = doc["project_id"] | "";
    status.project_name = doc["project_name"] | "";
    status.project_color = doc["project_color"] | "#888888";
    status.elapsed_seconds = doc["elapsed_seconds"] | 0;
    status.today_minutes = doc["today_minutes"] | 0;
    status.energy_leds = doc["energy_leds"] | 0;
    status.theme_accent = doc["theme_accent"] | "#E5A158";

    return true;
}

// startTimer / stopTimer omit the `time` field so the API's
// default_factory (datetime.now(UTC) on the server) records the
// real wall-clock moment the request landed. The previous code
// sent `{"time": "<millis-since-boot>"}` — a number like
// "12345" — which is not a parseable ISO 8601 datetime. Either
// the API was 422'ing every press, or it was accepting garbage
// timestamps and storing them. Server-side default is correct
// to within request latency (≤200ms over WiFi), which is
// imperceptible for time tracking.
bool ApiClient::startTimer(const String& projectId) {
    return httpPost("/api/projects/" + projectId + "/start");
}

bool ApiClient::stopTimer() {
    return httpPost("/api/projects/stop");
}

bool ApiClient::getFavorites(FavoriteProject* projects, int& count, int maxCount) {
    JsonDocument doc;
    if (!httpGet("/api/device/favorites", doc)) return false;

    JsonArray arr = doc.as<JsonArray>();
    count = 0;
    for (JsonObject obj : arr) {
        if (count >= maxCount) break;
        projects[count].id = obj["id"] | "";
        projects[count].name = obj["name"] | "";
        projects[count].color = obj["color"] | "#888888";
        count++;
    }
    return true;
}

bool ApiClient::postHeartbeat() {
    return httpPost("/api/device/heartbeat");
}

bool ApiClient::getDashboard(DeviceStatus& status, String& nextEvent, int& goalPct) {
    // Combines status with additional dashboard data
    if (!getStatus(status)) return false;
    nextEvent = "";
    goalPct = 0;
    return true;
}
