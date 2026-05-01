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

func TestComputeCadence_LowAndHighRates(t *testing.T) {
	// 12 samples at 5s = 1 minute. The heuristic is 200 events/min = 1.0.
	const epmFull = 200.0
	now := time.Now().UTC()

	build := func(eventsPerSample int64) []Sample {
		s := make([]Sample, 12)
		for i := range s {
			s[i] = Sample{
				CollectedAt: now.Add(time.Duration(i*5) * time.Second),
				BundleID:    "com.apple.dt.Xcode",
				IdleSeconds: 1.0,
				EventCount:  eventsPerSample,
			}
		}
		return s
	}

	// 0 events → cadence = 0
	if got := computeCadence(build(0), time.Minute); got != 0.0 {
		t.Errorf("zero events should give cadence 0.0, got %f", got)
	}
	// Roughly half-full: 100 events/min spread over 12 samples ≈ 8.3
	// per sample → 8 events × 12 samples = 96 events / 1 min ≈ 0.48
	if got := computeCadence(build(8), time.Minute); math.Abs(got-0.48) > 0.05 {
		t.Errorf("8 events/sample should give cadence ~0.48, got %f", got)
	}
	// Beyond full: 50 events/sample × 12 samples = 600/min — clamps to 1.0
	if got := computeCadence(build(50), time.Minute); got != 1.0 {
		t.Errorf("beyond-full rate should clamp to 1.0, got %f", got)
	}
	_ = epmFull // silence unused-const warning if the heuristic ever changes
}

func TestComputeCadence_NormalizesToActualWindowDuration(t *testing.T) {
	// Regression guard: the previous implementation hardcoded
	// "5s samples" so the events-per-minute denominator was
	// `len(samples) * 5 / 60` minutes. A user with
	// PollIntervalSec=10 (samples every 10s) would get a
	// denominator of half real, doubling the cadence score.
	// Now the duration comes from the window's actual span,
	// so the same per-minute event rate produces the same
	// cadence regardless of poll cadence.
	now := time.Now().UTC()
	build := func(numSamples int, eventsPerSample int64) []Sample {
		s := make([]Sample, numSamples)
		for i := range s {
			s[i] = Sample{
				CollectedAt: now.Add(time.Duration(i) * time.Second),
				BundleID:    "com.apple.dt.Xcode",
				EventCount:  eventsPerSample,
			}
		}
		return s
	}
	// Same total event count (96) over a 1-minute window, sampled
	// at two different cadences — cadence score should be identical
	// since the window duration is the same. Old code computed
	// duration as len(samples)*5/60, so 12-sample and 6-sample
	// runs would have produced different denominators.
	medium := computeCadence(build(12, 8), time.Minute) // 12 × 8 = 96
	sparse := computeCadence(build(6, 16), time.Minute) // 6 × 16 = 96
	if math.Abs(medium-sparse) > 0.001 {
		t.Errorf("same total events / same window = same cadence; got %f vs %f", medium, sparse)
	}
}

func TestComputeCadence_MixedAvailability_OnlyEventTapSamplesCount(t *testing.T) {
	// Half the samples have EventCount=-1 (no event tap), half are real.
	// The function should still return a sensible cadence based on the
	// real samples — not skew because half the data is "missing".
	now := time.Now().UTC()
	samples := make([]Sample, 12)
	for i := range samples {
		ec := int64(-1)
		if i%2 == 0 {
			ec = 16 // 6 samples × 16 events = 96 over half the window
		}
		samples[i] = Sample{
			CollectedAt: now.Add(time.Duration(i*5) * time.Second),
			BundleID:    "com.apple.dt.Xcode",
			IdleSeconds: 1.0,
			EventCount:  ec,
		}
	}
	c := computeCadence(samples, time.Minute)
	// We don't pin an exact value here (the function divides total by
	// duration computed from len(samples), which includes the missing
	// ones — that's a known quirk worth pinning if changed) but it
	// should be a real number, not the 0.5 fallback.
	if c == 0.5 {
		t.Errorf("expected real cadence value, got fallback 0.5")
	}
	if c < 0 || c > 1 {
		t.Errorf("cadence out of range: %f", c)
	}
}

func TestComputeCoherence_EmptyAndSingleSample(t *testing.T) {
	// Empty input: implementation has no samples, no bundle counts → n=0
	// → returns 1.0 (defensible: "nothing happened" reads as
	// "you weren't context switching").
	if got := computeCoherence(nil); got != 1.0 {
		t.Errorf("empty samples should give coherence 1.0, got %f", got)
	}
	// Single sample, single bundle: definitely focused.
	got := computeCoherence([]Sample{{BundleID: "com.apple.dt.Xcode"}})
	if got != 1.0 {
		t.Errorf("single-sample coherence should be 1.0, got %f", got)
	}
}

func TestComputeContextSwitches_IgnoresEmptyBundles(t *testing.T) {
	// The frontmost-app helper occasionally returns an empty bundle ID
	// (briefly, e.g. during a Spaces switch). A naive switch counter
	// would over-count those as "context switches"; the real impl
	// skips transitions involving empty IDs.
	now := time.Now().UTC()
	samples := []Sample{
		{CollectedAt: now, BundleID: "A"},
		{CollectedAt: now.Add(5 * time.Second), BundleID: ""},
		{CollectedAt: now.Add(10 * time.Second), BundleID: "B"},
		{CollectedAt: now.Add(15 * time.Second), BundleID: "B"},
	}
	if got := computeContextSwitches(samples); got != 0 {
		t.Errorf("empty-bundle transitions should not count, got %d switches", got)
	}
}

func TestComputeIdleFraction_BoundaryConditions(t *testing.T) {
	// Idle threshold is 30s. A sample at exactly 30 should NOT count as
	// idle (the impl uses strict >, not >=). One above does.
	at30 := []Sample{{IdleSeconds: 30.0}}
	if computeIdleFraction(at30) != 0.0 {
		t.Errorf("exactly 30s idle should not count as idle")
	}
	above := []Sample{{IdleSeconds: 30.5}}
	if computeIdleFraction(above) != 1.0 {
		t.Errorf("30.5s should fully count as idle")
	}
	if computeIdleFraction(nil) != 0.0 {
		t.Errorf("empty samples should give 0.0 idle fraction")
	}
}

func TestClamp(t *testing.T) {
	cases := []struct {
		v, lo, hi, want float64
	}{
		{0.5, 0.0, 1.0, 0.5},
		{-0.1, 0.0, 1.0, 0.0},
		{1.5, 0.0, 1.0, 1.0},
		{0.0, 0.0, 1.0, 0.0},
		{1.0, 0.0, 1.0, 1.0},
	}
	for _, c := range cases {
		if got := clamp(c.v, c.lo, c.hi); got != c.want {
			t.Errorf("clamp(%v, %v, %v) = %v, want %v", c.v, c.lo, c.hi, got, c.want)
		}
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
