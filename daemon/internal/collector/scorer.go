package collector

import (
	"math"
	"time"
)

const (
	// idleThresholdSec: a sample is considered "idle" if IdleSeconds exceeds this.
	idleThresholdSec = 30.0

	// Weights for the composite flow score.
	cadenceWeight   = 0.4
	coherenceWeight = 0.4
	categoryWeight  = 0.2
)

// ComputeFlowWindow computes a FlowWindow from a slice of samples.
//
// activeProjectID and projectCategory are empty if no timer is running.
// When the event tap is unavailable (all EventCount == -1), cadence defaults to 0.5.
func ComputeFlowWindow(
	samples []Sample,
	start, end time.Time,
	activeProjectID, projectCategory string,
) FlowWindow {
	w := FlowWindow{
		WindowStart:     start,
		WindowEnd:       end,
		ActiveProjectID: activeProjectID,
	}

	if len(samples) == 0 {
		w.CadenceScore = 0.5
		w.CoherenceScore = 0.5
		w.FlowScore = clamp(cadenceWeight*0.5+coherenceWeight*0.5, 0, 1)
		return w
	}

	w.CadenceScore = computeCadence(samples, end.Sub(start))
	w.CoherenceScore = computeCoherence(samples)
	w.DominantBundleID, w.DominantCategory = computeDominant(samples)
	w.CategoryFitScore = computeCategoryFit(w.DominantCategory, activeProjectID, projectCategory)
	w.IdleFraction = computeIdleFraction(samples)
	w.ContextSwitches = computeContextSwitches(samples)

	idlePenalty := math.Max(0, w.IdleFraction-0.2) * 1.25
	w.FlowScore = clamp(
		cadenceWeight*w.CadenceScore+
			coherenceWeight*w.CoherenceScore+
			categoryWeight*w.CategoryFitScore-
			idlePenalty,
		0, 1,
	)

	return w
}

// computeCadence returns the cadence score from input-event counts.
// If event tap data is unavailable (all EventCount == -1), returns 0.5.
//
// `windowDuration` is the wall-clock span of the flow window
// (typically the FlushIntervalSec config value). Used to normalize
// raw event counts into events-per-minute. Previously this code
// computed duration as `len(samples) * 5.0` seconds — a hardcoded
// 5s sample cadence that lied about reality whenever
// PollIntervalSec was reconfigured. A user setting
// PollIntervalSec=10 was getting cadence scores doubled
// (denominator was half what it should have been); 1s polling
// was getting cadence scores ⅕ of correct.
func computeCadence(samples []Sample, windowDuration time.Duration) float64 {
	var totalEvents int64
	var validSamples int
	for _, s := range samples {
		if s.EventCount >= 0 {
			totalEvents += s.EventCount
			validSamples++
		}
	}
	if validSamples == 0 {
		return 0.5 // no event tap data
	}

	// Normalize: assume ~200 events/min is "fully active" (reasonable for coding).
	// This is a rough heuristic; a personal median would be better.
	durationMin := windowDuration.Minutes()
	if durationMin <= 0 {
		return 0.5
	}
	epm := float64(totalEvents) / durationMin
	return clamp(epm/200.0, 0, 1)
}

// computeCoherence returns 1 − normalized entropy of the app distribution.
// 1.0 = single app (fully focused), 0.0 = maximum context switching.
func computeCoherence(samples []Sample) float64 {
	counts := make(map[string]int)
	for _, s := range samples {
		if s.BundleID != "" {
			counts[s.BundleID]++
		}
	}
	n := len(counts)
	if n <= 1 {
		return 1.0
	}

	total := float64(len(samples))
	var entropy float64
	for _, c := range counts {
		p := float64(c) / total
		if p > 0 {
			entropy -= p * math.Log2(p)
		}
	}
	maxEntropy := math.Log2(float64(n))
	if maxEntropy <= 0 {
		return 1.0
	}
	return clamp(1.0-entropy/maxEntropy, 0, 1)
}

// computeDominant returns the bundle ID and category of the most-seen app.
func computeDominant(samples []Sample) (bundleID, category string) {
	counts := make(map[string]int)
	for _, s := range samples {
		if s.BundleID != "" {
			counts[s.BundleID]++
		}
	}
	maxCount := 0
	for bid, c := range counts {
		if c > maxCount {
			maxCount = c
			bundleID = bid
		}
	}
	category = CategoryFor(bundleID)
	return bundleID, category
}

// computeCategoryFit returns 1.0 if the dominant app category matches the project category,
// 0.0 otherwise. Returns 0.0 if no timer is running.
func computeCategoryFit(dominantCategory, activeProjectID, projectCategory string) float64 {
	if activeProjectID == "" || projectCategory == "" {
		return 0.0
	}
	if dominantCategory == projectCategory {
		return 1.0
	}
	return 0.0
}

// computeIdleFraction returns the fraction of samples where idle time exceeds the threshold.
func computeIdleFraction(samples []Sample) float64 {
	if len(samples) == 0 {
		return 0.0
	}
	idle := 0
	for _, s := range samples {
		if s.IdleSeconds > idleThresholdSec {
			idle++
		}
	}
	return float64(idle) / float64(len(samples))
}

// computeContextSwitches counts how many times the active app changed between consecutive samples.
func computeContextSwitches(samples []Sample) int {
	switches := 0
	for i := 1; i < len(samples); i++ {
		if samples[i].BundleID != samples[i-1].BundleID &&
			samples[i].BundleID != "" && samples[i-1].BundleID != "" {
			switches++
		}
	}
	return switches
}

func clamp(v, lo, hi float64) float64 {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}
