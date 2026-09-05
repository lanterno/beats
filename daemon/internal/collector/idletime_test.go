package collector

import (
	"math"
	"testing"
)

func TestParseIdleTime(t *testing.T) {
	output := `      | |   "HIDIdleTime" = 5000000000
`
	got := parseIdleTime(output)
	if math.Abs(got-5.0) > 0.001 {
		t.Errorf("expected 5.0s, got %f", got)
	}
}

func TestParseIdleTime_LargeValue(t *testing.T) {
	output := `    |   |   "HIDIdleTime" = 123456789012345
`
	got := parseIdleTime(output)
	expected := 123456.789012345
	if math.Abs(got-expected) > 0.001 {
		t.Errorf("expected %f, got %f", expected, got)
	}
}

func TestParseIdleTime_NoMatch(t *testing.T) {
	got := parseIdleTime("no idle time here")
	if got != 0.0 {
		t.Errorf("expected 0.0 for no match, got %f", got)
	}
}

func TestParseIdleTime_Empty(t *testing.T) {
	got := parseIdleTime("")
	if got != 0.0 {
		t.Errorf("expected 0.0 for empty, got %f", got)
	}
}

func TestParseIdleTime_MultipleLines(t *testing.T) {
	// Real ioreg output has multiple lines; we want the one with the value
	output := `      | |   "HIDIdleTime" = 2500000000
      | |   "HIDIdleTime" = 2500000000
`
	got := parseIdleTime(output)
	if math.Abs(got-2.5) > 0.001 {
		t.Errorf("expected 2.5s, got %f", got)
	}
}

func TestIdleSecondsFromTicks(t *testing.T) {
	tests := []struct {
		name      string
		nowTicks  uint64
		lastInput uint32
		want      float64
	}{
		{
			name:      "input just now",
			nowTicks:  1_000_000,
			lastInput: 1_000_000,
			want:      0.0,
		},
		{
			name:      "idle 5 seconds",
			nowTicks:  1_005_000,
			lastInput: 1_000_000,
			want:      5.0,
		},
		{
			name:      "idle past the 30s collector threshold",
			nowTicks:  1_045_000,
			lastInput: 1_000_000,
			want:      45.0,
		},
		{
			// The case this helper exists for. GetTickCount64 keeps
			// counting past 2^32 while LASTINPUTINFO.dwTime wraps, so
			// after ~49.7 days of uptime the two are on different
			// sides of the boundary. Truncating now to uint32 makes
			// the subtraction wrap in lockstep and stay correct;
			// widening dwTime instead would report a ~49-day idle.
			name:      "uptime past the uint32 tick rollover",
			nowTicks:  1<<32 + 3_000, // 3s after the wrap
			lastInput: 0xFFFFFFFF - 1_999,
			want:      5.0, // 2s before the wrap + 3s after
		},
		{
			name:      "last input marginally ahead of now is treated as active",
			nowTicks:  1_000_000,
			lastInput: 1_000_050,
			want:      0.0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := idleSecondsFromTicks(tt.nowTicks, tt.lastInput)
			if math.Abs(got-tt.want) > 0.001 {
				t.Errorf("idleSecondsFromTicks(%d, %d) = %f, want %f",
					tt.nowTicks, tt.lastInput, got, tt.want)
			}
		})
	}
}
