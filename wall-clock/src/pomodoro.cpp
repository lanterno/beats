#include "pomodoro.h"

void Pomodoro::start() {
    _state = PomodoroState::WORKING;
    _phaseStartMs = millis();
    _phaseDurationMs = POMODORO_WORK_MS;
}

void Pomodoro::stop() {
    _state = PomodoroState::INACTIVE;
}

bool Pomodoro::update() {
    if (_state == PomodoroState::INACTIVE) return false;

    unsigned long elapsed = millis() - _phaseStartMs;
    if (elapsed >= _phaseDurationMs) {
        // Transition
        if (_state == PomodoroState::WORKING) {
            _state = PomodoroState::BREAK;
            _phaseStartMs = millis();
            _phaseDurationMs = POMODORO_BREAK_MS;
            return true;
        } else {
            // Break finished — go back to working
            _state = PomodoroState::WORKING;
            _phaseStartMs = millis();
            _phaseDurationMs = POMODORO_WORK_MS;
            return true;
        }
    }
    return false;
}

int Pomodoro::remainingSeconds() const {
    if (_state == PomodoroState::INACTIVE) return 0;
    unsigned long elapsed = millis() - _phaseStartMs;
    if (elapsed >= _phaseDurationMs) return 0;
    return (_phaseDurationMs - elapsed) / 1000;
}
