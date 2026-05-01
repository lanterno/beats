#pragma once

#include <FastLED.h>
#include "config.h"

class LedStrip {
public:
    void begin();

    // Set all LEDs to a single color
    void setColor(CRGB color);

    // Energy meter: fill LEDs 0..count-1 with color, rest off
    void showEnergyMeter(int count, CRGB color);

    // Progress bar: fill proportionally (0.0 - 1.0)
    void showProgressBar(float progress, CRGB color);

    // Pulse animation (call in loop)
    void pulseAnimation(CRGB baseColor, unsigned long now);

    // Smooth fade to off
    void fadeToBlack(int steps = 30);

    // Brief red flash for transient errors (e.g. timer start failed).
    // Caller is responsible for restoring the post-flash state — typical
    // pattern is to force a status refresh, which repaints from truth.
    void flashError(int blinks = 3, int onMs = 120, int offMs = 100);

    // Color transitions: active vs idle
    void setActiveColor(CRGB projectColor);
    void setIdleColor(CRGB projectColor);

    void clear();
    void show();

private:
    CRGB _leds[NUM_LEDS];
    uint8_t _pulsePhase = 0;
};
