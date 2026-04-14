#pragma once

#include <Arduino.h>
#include "config.h"

enum class PomodoroState {
    INACTIVE,
    WORKING,
    BREAK,
};

class Pomodoro {
public:
    void start();
    void stop();

    // Call in loop — returns true when state changes
    bool update();

    PomodoroState state() const { return _state; }
    int remainingSeconds() const;
    bool isBreak() const { return _state == PomodoroState::BREAK; }

private:
    PomodoroState _state = PomodoroState::INACTIVE;
    unsigned long _phaseStartMs = 0;
    unsigned long _phaseDurationMs = 0;
};
