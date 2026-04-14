#include "button.h"

Button::Button(uint8_t pin) : _pin(pin) {}

void Button::begin() {
    pinMode(_pin, INPUT_PULLUP);
}

ButtonEvent Button::update() {
    bool currentState = digitalRead(_pin);
    unsigned long now = millis();

    // Detect press (HIGH -> LOW with pullup)
    if (_lastState == HIGH && currentState == LOW) {
        _pressTime = now;
        _pressed = true;
        _longPressFired = false;
    }

    // Detect long press while held
    if (_pressed && currentState == LOW && !_longPressFired) {
        if (now - _pressTime >= LONG_PRESS_MS) {
            _longPressFired = true;
            _pressCount = 0;
            _lastState = currentState;
            return ButtonEvent::LONG_PRESS;
        }
    }

    // Detect release (LOW -> HIGH)
    if (_lastState == LOW && currentState == HIGH && _pressed) {
        _pressed = false;
        if (!_longPressFired && (now - _pressTime >= DEBOUNCE_MS)) {
            _pressCount++;
            _releaseTime = now;
        }
    }

    // Evaluate press count after double-press window expires
    if (_pressCount > 0 && !_pressed && (now - _releaseTime >= DOUBLE_PRESS_WINDOW_MS)) {
        ButtonEvent event = (_pressCount >= 2)
            ? ButtonEvent::DOUBLE_PRESS
            : ButtonEvent::SINGLE_PRESS;
        _pressCount = 0;
        _lastState = currentState;
        return event;
    }

    _lastState = currentState;
    return ButtonEvent::NONE;
}
