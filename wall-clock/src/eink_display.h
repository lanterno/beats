#pragma once

#include <Arduino.h>
#include "api_client.h"

enum class DisplayMode {
    ACTIVE_TIMER,   // Project name, elapsed time, today total
    IDLE_SUMMARY,   // Today's total, weekly goal progress
    CLOCK,          // Minimal clock face with today total
    WEEKLY_PROGRESS,// Weekly breakdown
    POMODORO,       // Countdown timer
    DOCK,           // Charging dock: clock + today total + battery
};

class EinkDisplay {
public:
    void begin();

    // Render different layouts
    void showActiveTimer(const String& projectName, int elapsedSeconds,
                         int todayMinutes, int goalPct);
    void showIdleSummary(int todayMinutes, int weekMinutes, int goalPct);
    void showClock(int todayMinutes);
    void showWeeklyProgress(int dayMinutes[7]);
    void showPomodoro(int remainingSeconds, bool isBreak);
    void showDock(int todayMinutes, int batteryPct);

    // Status line at bottom
    void showStatusLine(const String& text);

private:
    void clearAndPrepare();
    void drawCenteredText(const String& text, int y, int size = 1);
    void drawProgressBar(int x, int y, int w, int h, float progress);
    String formatTime(int seconds);
    String formatDuration(int minutes);
};
