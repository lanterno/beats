#include "eink_display.h"
#include "config.h"

// GxEPD2 for Waveshare 2.9" b/w (296x128)
#include <GxEPD2_BW.h>
#include <Fonts/FreeMonoBold12pt7b.h>
#include <Fonts/FreeMonoBold18pt7b.h>
#include <Fonts/FreeMono9pt7b.h>

// Display instance — Waveshare 2.9" B/W
static GxEPD2_BW<GxEPD2_290_T94_V2, GxEPD2_290_T94_V2::HEIGHT>
    display(GxEPD2_290_T94_V2(EINK_CS, EINK_DC, EINK_RST, EINK_BUSY));

void EinkDisplay::begin() {
    display.init(115200);
    display.setRotation(1);  // Landscape
    display.setTextColor(GxEPD_BLACK);
    display.setFullWindow();
    display.fillScreen(GxEPD_WHITE);
    display.display();
}

void EinkDisplay::clearAndPrepare() {
    display.setFullWindow();
    display.fillScreen(GxEPD_WHITE);
}

void EinkDisplay::drawCenteredText(const String& text, int y, int size) {
    if (size == 2) {
        display.setFont(&FreeMonoBold18pt7b);
    } else if (size == 1) {
        display.setFont(&FreeMonoBold12pt7b);
    } else {
        display.setFont(&FreeMono9pt7b);
    }

    int16_t x1, y1;
    uint16_t w, h;
    display.getTextBounds(text, 0, 0, &x1, &y1, &w, &h);
    display.setCursor((display.width() - w) / 2, y);
    display.print(text);
}

void EinkDisplay::drawProgressBar(int x, int y, int w, int h, float progress) {
    display.drawRect(x, y, w, h, GxEPD_BLACK);
    int filled = (int)(progress * (w - 4));
    display.fillRect(x + 2, y + 2, filled, h - 4, GxEPD_BLACK);
}

String EinkDisplay::formatTime(int seconds) {
    int h = seconds / 3600;
    int m = (seconds % 3600) / 60;
    int s = seconds % 60;
    char buf[16];
    snprintf(buf, sizeof(buf), "%d:%02d:%02d", h, m, s);
    return String(buf);
}

String EinkDisplay::formatDuration(int minutes) {
    if (minutes >= 60) {
        int h = minutes / 60;
        int m = minutes % 60;
        char buf[16];
        snprintf(buf, sizeof(buf), "%dh %dm", h, m);
        return String(buf);
    }
    return String(minutes) + "m";
}

void EinkDisplay::showActiveTimer(const String& projectName, int elapsedSeconds,
                                   int todayMinutes, int goalPct) {
    clearAndPrepare();

    // Project name
    drawCenteredText(projectName, 30, 1);

    // Elapsed time (large)
    drawCenteredText(formatTime(elapsedSeconds), 70, 2);

    // Today's total
    display.setFont(&FreeMono9pt7b);
    String todayStr = "Today: " + formatDuration(todayMinutes);
    drawCenteredText(todayStr, 100, 0);

    // Goal progress bar
    if (goalPct > 0) {
        float progress = constrain(goalPct / 100.0f, 0.0f, 1.0f);
        drawProgressBar(40, 110, display.width() - 80, 10, progress);
    }

    display.display();
}

void EinkDisplay::showIdleSummary(int todayMinutes, int weekMinutes, int goalPct) {
    clearAndPrepare();

    drawCenteredText("Today", 25, 0);
    drawCenteredText(formatDuration(todayMinutes), 55, 2);

    display.setFont(&FreeMono9pt7b);
    String weekStr = "This week: " + formatDuration(weekMinutes);
    drawCenteredText(weekStr, 85, 0);

    if (goalPct > 0) {
        float progress = constrain(goalPct / 100.0f, 0.0f, 1.0f);
        drawProgressBar(40, 100, display.width() - 80, 10, progress);
    }

    display.display();
}

void EinkDisplay::showClock(int todayMinutes) {
    clearAndPrepare();

    // Current time. getLocalTime returns false if NTP hasn't synced
    // yet (default 5s wait); without the check, timeinfo's
    // tm_hour/tm_min are uninitialized stack and the display
    // could show anything from 00:00 to 99:99. Render "--:--"
    // until sync completes so the user knows to wait.
    struct tm timeinfo;
    char timeBuf[8];
    if (getLocalTime(&timeinfo)) {
        snprintf(timeBuf, sizeof(timeBuf), "%02d:%02d", timeinfo.tm_hour, timeinfo.tm_min);
    } else {
        snprintf(timeBuf, sizeof(timeBuf), "--:--");
    }
    drawCenteredText(String(timeBuf), 60, 2);

    // Today's total below
    String todayStr = formatDuration(todayMinutes);
    drawCenteredText(todayStr, 100, 0);

    display.display();
}

void EinkDisplay::showWeeklyProgress(int dayMinutes[7]) {
    clearAndPrepare();

    const char* days[] = {"M", "T", "W", "T", "F", "S", "S"};
    int maxMin = 1;
    for (int i = 0; i < 7; i++) {
        if (dayMinutes[i] > maxMin) maxMin = dayMinutes[i];
    }

    int barWidth = 30;
    int gap = 6;
    int startX = (display.width() - (7 * barWidth + 6 * gap)) / 2;
    int barMaxH = 80;

    display.setFont(&FreeMono9pt7b);
    for (int i = 0; i < 7; i++) {
        int x = startX + i * (barWidth + gap);
        int barH = (int)((float)dayMinutes[i] / maxMin * barMaxH);
        barH = max(barH, 2);

        // Bar
        display.fillRect(x, 10 + barMaxH - barH, barWidth, barH, GxEPD_BLACK);

        // Day label
        int16_t x1, y1;
        uint16_t w, h;
        display.getTextBounds(days[i], 0, 0, &x1, &y1, &w, &h);
        display.setCursor(x + (barWidth - w) / 2, 108);
        display.print(days[i]);
    }

    display.display();
}

void EinkDisplay::showPomodoro(int remainingSeconds, bool isBreak) {
    clearAndPrepare();

    drawCenteredText(isBreak ? "Break" : "Focus", 30, 1);
    drawCenteredText(formatTime(remainingSeconds), 70, 2);

    float progress = 1.0f - (float)remainingSeconds /
        (isBreak ? (POMODORO_BREAK_MS / 1000) : (POMODORO_WORK_MS / 1000));
    drawProgressBar(40, 95, display.width() - 80, 12, progress);

    display.display();
}

void EinkDisplay::showDock(int todayMinutes, int batteryPct) {
    clearAndPrepare();

    // Clock — same NTP-not-synced guard as showClock; without it
    // the dock view could render uninitialized hour/minute fields
    // when the device boots into the dock state before sync.
    struct tm timeinfo;
    char timeBuf[8];
    if (getLocalTime(&timeinfo)) {
        snprintf(timeBuf, sizeof(timeBuf), "%02d:%02d", timeinfo.tm_hour, timeinfo.tm_min);
    } else {
        snprintf(timeBuf, sizeof(timeBuf), "--:--");
    }
    drawCenteredText(String(timeBuf), 55, 2);

    // Today's total
    drawCenteredText(formatDuration(todayMinutes), 90, 0);

    // Battery in corner
    display.setFont(&FreeMono9pt7b);
    char batBuf[8];
    snprintf(batBuf, sizeof(batBuf), "%d%%", batteryPct);
    display.setCursor(display.width() - 50, 120);
    display.print(batBuf);

    display.display();
}

void EinkDisplay::showStatusLine(const String& text) {
    // Partial update — just the bottom 16px
    display.setFont(&FreeMono9pt7b);
    display.setPartialWindow(0, display.height() - 16, display.width(), 16);
    display.fillScreen(GxEPD_WHITE);
    display.setCursor(4, display.height() - 4);
    display.print(text);
    display.display(true);  // Partial update
}
