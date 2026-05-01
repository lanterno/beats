#include "led_strip.h"

void LedStrip::begin() {
    FastLED.addLeds<WS2812B, LED_PIN, GRB>(_leds, NUM_LEDS);
    FastLED.setBrightness(60);
    clear();
    show();
}

void LedStrip::setColor(CRGB color) {
    fill_solid(_leds, NUM_LEDS, color);
    show();
}

void LedStrip::showEnergyMeter(int count, CRGB color) {
    clear();
    int n = constrain(count, 0, NUM_LEDS);
    for (int i = 0; i < n; i++) {
        _leds[i] = color;
    }
    show();
}

void LedStrip::showProgressBar(float progress, CRGB color) {
    clear();
    float filled = progress * NUM_LEDS;
    for (int i = 0; i < NUM_LEDS; i++) {
        if (i < (int)filled) {
            _leds[i] = color;
        } else if (i == (int)filled) {
            // Partial fill for the transition LED
            uint8_t frac = (uint8_t)((filled - (int)filled) * 255);
            _leds[i] = color;
            _leds[i].nscale8(frac);
        }
    }
    show();
}

void LedStrip::pulseAnimation(CRGB baseColor, unsigned long now) {
    // Gentle sine wave pulse
    uint8_t brightness = beatsin8(30, 20, 80);  // 30 BPM, range 20-80
    fill_solid(_leds, NUM_LEDS, baseColor);
    FastLED.setBrightness(brightness);
    show();
    FastLED.setBrightness(60);  // Reset default
}

void LedStrip::fadeToBlack(int steps) {
    for (int s = 0; s < steps; s++) {
        for (int i = 0; i < NUM_LEDS; i++) {
            _leds[i].fadeToBlackBy(256 / steps);
        }
        show();
        delay(30);
    }
    clear();
    show();
}

void LedStrip::flashError(int blinks, int onMs, int offMs) {
    for (int i = 0; i < blinks; i++) {
        fill_solid(_leds, NUM_LEDS, CRGB::Red);
        show();
        delay(onMs);
        clear();
        show();
        if (i < blinks - 1) delay(offMs);
    }
}

void LedStrip::setActiveColor(CRGB projectColor) {
    setColor(projectColor);
}

void LedStrip::setIdleColor(CRGB projectColor) {
    // Desaturate and dim for idle state
    CRGB muted = projectColor;
    muted.nscale8(40);  // 15% brightness
    setColor(muted);
}

void LedStrip::clear() {
    fill_solid(_leds, NUM_LEDS, CRGB::Black);
}

void LedStrip::show() {
    FastLED.show();
}
