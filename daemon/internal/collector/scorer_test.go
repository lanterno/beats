package collector

import (
	"math"
	"testing"
	"time"
)

func TestComputeFlowWindow_EmptySamples(t *testing.T) {
	now := time.Now().UTC()
	w := ComputeFlowWindow(nil, now, now.Add(time.Minute), "", "")

	if w.CadenceScore != 0.5 {
		t.Errorf("expected cadence 0.5 for empty, got %f", w.CadenceScore)
	}
	if w.CoherenceScore != 0.5 {
		t.Errorf("expected coherence 0.5 for empty, got %f", w.CoherenceScore)
	}
	if w.FlowScore < 0 || w.FlowScore > 1 {
		t.Errorf("flow score out of range: %f", w.FlowScore)
	}
}

func TestComputeFlowWindow_SingleApp_NotIdle(t *testing.T) {
	now := time.Now().UTC()
	samples := make([]Sample, 12)
	for i := range samples {
		samples[i] = Sample{
			CollectedAt: now.Add(time.Duration(i*5) * time.Second),
			BundleID:    "com.microsoft.VSCode",
			AppName:     "Visual Studio Code",
			IdleSeconds: 2.0,
			EventCount:  -1, // no event tap
		}
	}

	w := ComputeFlowWindow(samples, now, now.Add(time.Minute), "", "")

	if w.CoherenceScore != 1.0 {
		t.Errorf("expected coherence 1.0 for single app, got %f", w.CoherenceScore)
	}
	if w.IdleFraction != 0.0 {
		t.Errorf("expected idle fraction 0.0, got %f", w.IdleFraction)
	}
	if w.DominantBundleID != "com.microsoft.VSCode" {
		t.Errorf("expected dominant VS Code, got %s", w.DominantBundleID)
	}
	if w.DominantCategory != "coding" {
		t.Errorf("expected category coding, got %s", w.DominantCategory)
	}
	if w.ContextSwitches != 0 {
		t.Errorf("expected 0 context switches, got %d", w.ContextSwitches)
	}
	// With no event tap: cadence=0.5, coherence=1.0, catfit=0.0 (no timer)
	// Score = 0.4*0.5 + 0.4*1.0 + 0.2*0.0 = 0.6
	if math.Abs(w.FlowScore-0.6) > 0.01 {
		t.Errorf("expected flow score ~0.6, got %f", w.FlowScore)
	}
}

func TestComputeFlowWindow_MultipleApps_HighEntropy(t *testing.T) {
	now := time.Now().UTC()
	apps := []string{
		"com.microsoft.VSCode",
		"com.tinyspeck.slackmacgap",
		"com.google.Chrome",
		"com.apple.mail",
	}
	var samples []Sample
	for i := 0; i < 12; i++ {
		samples = append(samples, Sample{
			CollectedAt: now.Add(time.Duration(i*5) * time.Second),
			BundleID:    apps[i%len(apps)],
			AppName:     "app",
			IdleSeconds: 1.0,
			EventCount:  -1,
		})
	}

	w := ComputeFlowWindow(samples, now, now.Add(time.Minute), "", "")

	// 4 apps with equal distribution: entropy is maximal, coherence should be low
	if w.CoherenceScore > 0.1 {
		t.Errorf("expected low coherence for 4 equal apps, got %f", w.CoherenceScore)
	}
	// Many context switches
	if w.ContextSwitches < 8 {
		t.Errorf("expected many context switches, got %d", w.ContextSwitches)
	}
}

func TestComputeFlowWindow_WithIdlePenalty(t *testing.T) {
	now := time.Now().UTC()
	var samples []Sample
	for i := 0; i < 10; i++ {
		idle := 1.0
		if i >= 5 { // 50% idle
			idle = 60.0
		}
		samples = append(samples, Sample{
			CollectedAt: now.Add(time.Duration(i*5) * time.Second),
			BundleID:    "com.apple.dt.Xcode",
			AppName:     "Xcode",
			IdleSeconds: idle,
			EventCount:  -1,
		})
	}

	w := ComputeFlowWindow(samples, now, now.Add(50*time.Second), "", "")

	if math.Abs(w.IdleFraction-0.5) > 0.01 {
		t.Errorf("expected idle fraction 0.5, got %f", w.IdleFraction)
	}
	// idle_penalty = max(0, 0.5 - 0.2) * 1.25 = 0.375
	// Without penalty: 0.4*0.5 + 0.4*1.0 + 0.2*0.0 = 0.6
	// With penalty: 0.6 - 0.375 = 0.225
	if math.Abs(w.FlowScore-0.225) > 0.02 {
		t.Errorf("expected flow score ~0.225 with idle penalty, got %f", w.FlowScore)
	}
}

func TestComputeFlowWindow_CategoryFit(t *testing.T) {
	now := time.Now().UTC()
	samples := []Sample{{
		CollectedAt: now,
		BundleID:    "com.apple.dt.Xcode",
		AppName:     "Xcode",
		IdleSeconds: 0,
		EventCount:  -1,
	}}

	// Timer running on a coding project
	w := ComputeFlowWindow(samples, now, now.Add(5*time.Second), "proj-123", "coding")
	if w.CategoryFitScore != 1.0 {
		t.Errorf("expected category fit 1.0 for coding match, got %f", w.CategoryFitScore)
	}

	// Timer running on a design project (mismatch)
	w = ComputeFlowWindow(samples, now, now.Add(5*time.Second), "proj-456", "design")
	if w.CategoryFitScore != 0.0 {
		t.Errorf("expected category fit 0.0 for mismatch, got %f", w.CategoryFitScore)
	}

	// No timer running
	w = ComputeFlowWindow(samples, now, now.Add(5*time.Second), "", "")
	if w.CategoryFitScore != 0.0 {
		t.Errorf("expected category fit 0.0 with no timer, got %f", w.CategoryFitScore)
	}
}
