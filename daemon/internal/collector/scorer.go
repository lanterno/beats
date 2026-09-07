package collector

import (
	"math"
	"time"
)

// Shipped scoring defaults, used whenever daemon.toml leaves a tunable at zero.
//
// The three weights compose the flow score: a weighted sum of cadence,
// coherence and category-fit, minus an idle penalty. They sum to 1.0 here; the
// final score clamps to [0,1], so a weights table exceeding 1.0 just flattens
// at the top and one summing below leaves headroom unused. IdleThreshold is the
// per-sample gate — a sample with IdleSeconds above it counts as idle.
const (
	defaultCadenceWeight    = 0.4
	defaultCoherenceWeight  = 0.4
	defaultCategoryWeight   = 0.2
	defaultIdleThresholdSec = 30.0
)

// ScoringParams mirrors config.ScoringConfig but is package-local so the
// collector does not depend on the config package.
type ScoringParams struct {
	CadenceWeight    float64
	CoherenceWeight  float64
	CategoryWeight   float64
	IdleThresholdSec float64
}

// Scorer turns samples into flow windows using one fixed set of tunables.
//
// These used to be package-level vars reconfigured at startup, which made the
// weights process-global: two Scorers were impossible, and the doc comment had
// to warn that reconfiguring mid-run was a race. Holding them on a value built
// once removes both problems.
type Scorer struct {
	cadenceWeight    float64
	coherenceWeight  float64
	categoryWeight   float64
	idleThresholdSec float64
}

// NewScorer builds a Scorer from the [scoring] section of daemon.toml. A zero
// field means "keep the shipped default", so a config file without the section
// — or with only some of it filled in — behaves exactly as before.
func NewScorer(p ScoringParams) *Scorer {
	s := &Scorer{
		cadenceWeight:    defaultCadenceWeight,
		coherenceWeight:  defaultCoherenceWeight,
		categoryWeight:   defaultCategoryWeight,
		idleThresholdSec: defaultIdleThresholdSec,
	}
	if p.CadenceWeight > 0 {
		s.cadenceWeight = p.CadenceWeight
	}
	if p.CoherenceWeight > 0 {
		s.coherenceWeight = p.CoherenceWeight
	}
	if p.CategoryWeight > 0 {
		s.categoryWeight = p.CategoryWeight
	}
	if p.IdleThresholdSec > 0 {
		s.idleThresholdSec = p.IdleThresholdSec
	}
	return s
}

// DefaultScorer is the Scorer a stock daemon.toml produces.
func DefaultScorer() *Scorer { return NewScorer(ScoringParams{}) }

// ComputeFlowWindow computes a FlowWindow from a slice of samples.
//
// activeProjectID and projectCategory are empty if no timer is running.
// When the event tap is unavailable (all EventCount == -1), cadence defaults to 0.5.
func (sc *Scorer) ComputeFlowWindow(
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
		w.FlowScore = clamp(sc.cadenceWeight*0.5+sc.coherenceWeight*0.5, 0, 1)
		return w
	}

	w.CadenceScore = computeCadence(samples, end.Sub(start))
	w.CoherenceScore = computeCoherence(samples)
	w.DominantBundleID, w.DominantCategory = computeDominant(samples)
	w.CategoryFitScore = computeCategoryFit(w.DominantCategory, activeProjectID, projectCategory)
	w.IdleFraction = sc.computeIdleFraction(samples)
	w.ContextSwitches = computeContextSwitches(samples)

	idlePenalty := math.Max(0, w.IdleFraction-0.2) * 1.25
	w.FlowScore = clamp(
		sc.cadenceWeight*w.CadenceScore+
			sc.coherenceWeight*w.CoherenceScore+
			sc.categoryWeight*w.CategoryFitScore-
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
//
// Zero observed apps is NOT full coherence. This used to fold n == 0
// into the n <= 1 branch and return 1.0, which meant "app detection
// produced nothing all window" scored identically to "the user never
// left their editor". On a platform where FrontmostApp always returns
// empty that is not a rounding error — it pins every flow window at
// exactly 0.600 (0.4 cadence fallback + 0.4 phantom coherence + 0
// category fit) and writes confident-looking fabricated data forever,
// with no error anywhere to notice.
//
// So n == 0 returns the same 0.5 "unknown" the cadence fallback and
// the empty-window path already use. A blind window now reads 0.400,
// which is at least honestly mid-range rather than a claim of ideal
// focus. `beatsd doctor`'s signal-sources check is the loud half of
// this fix; this is the quiet half that holds when detection breaks
// after startup.
func computeCoherence(samples []Sample) float64 {
	counts := make(map[string]int)
	for _, s := range samples {
		if s.BundleID != "" {
			counts[s.BundleID]++
		}
	}
	n := len(counts)
	if n == 0 {
		return 0.5
	}
	if n == 1 {
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
func (sc *Scorer) computeIdleFraction(samples []Sample) float64 {
	if len(samples) == 0 {
		return 0.0
	}
	idle := 0
	for _, s := range samples {
		if s.IdleSeconds > sc.idleThresholdSec {
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
