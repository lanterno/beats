#pragma once

#include <Arduino.h>
#include "config.h"

enum class ButtonEvent {
    NONE,
    SINGLE_PRESS,
    DOUBLE_PRESS,
    LONG_PRESS,
};

class Button {
public:
    Button(uint8_t pin);

    void begin();

    // Call in loop() — returns the detected event
    ButtonEvent update();

private:
    uint8_t _pin;
    bool _lastState = HIGH;
    bool _pressed = false;
    unsigned long _pressTime = 0;
    unsigned long _releaseTime = 0;
    int _pressCount = 0;
    bool _longPressFired = false;
};
