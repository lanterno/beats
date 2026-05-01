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

// rgbFromArray reads a 3-element JSON int array (e.g.
// "project_color_rgb": [91, 156, 246]) into a CRGB. Defaults
// fall back to gray on missing/malformed input. The API has
// emitted RGB triplets since the WebAuthn-era device router
// shipped — earlier firmware was reading the never-existed
// "project_color" string key and getting "#888888" defaults
// for everything.
static CRGB rgbFromArray(JsonVariant arr, uint8_t r0, uint8_t g0, uint8_t b0) {
    if (!arr.is<JsonArray>() || arr.size() < 3) {
        return CRGB(r0, g0, b0);
    }
    return CRGB((uint8_t)(arr[0] | r0), (uint8_t)(arr[1] | g0), (uint8_t)(arr[2] | b0));
}

bool ApiClient::getStatus(DeviceStatus& status) {
    JsonDocument doc;
    if (!httpGet("/api/device/status", doc)) return false;

    // API contract is the DeviceStatusResponse pydantic model in
    // api/src/beats/api/routers/device.py. Field names there
    // (clocked_in, daily_total_minutes, energy_level,
    // project_color_rgb, theme_accent_rgb, elapsed_minutes) drift
    // intentionally from the firmware-side names — the parser
    // here is the single point of translation so a future API
    // shape change breaks compile-time, not run-time silently.
    status.is_active = doc["clocked_in"] | false;
    status.project_id = doc["project_id"] | "";
    status.project_name = doc["project_name"] | "";
    status.project_color = rgbFromArray(doc["project_color_rgb"], 0x88, 0x88, 0x88);
    status.elapsed_minutes = doc["elapsed_minutes"] | 0;
    status.today_minutes = doc["daily_total_minutes"] | 0;
    status.energy_leds = doc["energy_level"] | 0;
    status.theme_accent = rgbFromArray(doc["theme_accent_rgb"], 0xE5, 0xA1, 0x58);

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
        // API sends color_rgb as a 3-int list (DeviceFavoriteProject
        // pydantic model). Older firmware was reading "color" as a
        // hex string and getting "#888888" defaults for every favorite.
        projects[count].color = rgbFromArray(obj["color_rgb"], 0x88, 0x88, 0x88);
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
