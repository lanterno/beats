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
