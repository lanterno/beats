package collector

import (
	"context"
	"errors"
	"testing"
	"time"
)

// win builds a uniquely-identifiable FlowWindow. WindowStart is used as the
// identity key in assertions.
func win(id int) FlowWindow {
	base := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	return FlowWindow{WindowStart: base.Add(time.Duration(id) * time.Minute)}
}

// recordingPoster captures every window it's asked to send and can be
// toggled between failing and succeeding to simulate a transient outage.
type recordingPoster struct {
	fail bool
	sent []FlowWindow
}

func (p *recordingPoster) send(_ context.Context, w FlowWindow) error {
	if p.fail {
		return errors.New("network down")
	}
	p.sent = append(p.sent, w)
	return nil
}

func TestRetryBuffer_FailureEnqueues(t *testing.T) {
	p := &recordingPoster{fail: true}
	b := NewRetryBuffer(8)

	if err := b.Send(context.Background(), p.send, win(1)); err == nil {
		t.Fatal("expected Send to return the poster error")
	}
	if b.Len() != 1 {
		t.Fatalf("expected 1 buffered window after failure, got %d", b.Len())
	}
	if len(p.sent) != 0 {
		t.Fatalf("expected 0 windows delivered, got %d", len(p.sent))
	}
}

func TestRetryBuffer_SubsequentSuccessDrains(t *testing.T) {
	p := &recordingPoster{fail: true}
	b := NewRetryBuffer(8)

	// Two failures buffer two windows.
	_ = b.Send(context.Background(), p.send, win(1))
	_ = b.Send(context.Background(), p.send, win(2))
	if b.Len() != 2 {
		t.Fatalf("expected 2 buffered, got %d", b.Len())
	}

	// Recover: the next Send should drain the backlog (oldest first)
	// then deliver the current window.
	p.fail = false
	if err := b.Send(context.Background(), p.send, win(3)); err != nil {
		t.Fatalf("expected success after recovery, got %v", err)
	}
	if b.Len() != 0 {
		t.Fatalf("expected drained buffer, got %d", b.Len())
	}

	// Windows must land in chronological order: 1, 2, then current 3.
	got := []time.Time{}
	for _, w := range p.sent {
		got = append(got, w.WindowStart)
	}
	want := []time.Time{win(1).WindowStart, win(2).WindowStart, win(3).WindowStart}
	if len(got) != len(want) {
		t.Fatalf("expected %d delivered, got %d", len(want), len(got))
	}
	for i := range want {
		if !got[i].Equal(want[i]) {
			t.Errorf("delivery order wrong at %d: got %v want %v", i, got[i], want[i])
		}
	}
}

func TestRetryBuffer_CapEvictsOldest(t *testing.T) {
	p := &recordingPoster{fail: true}
	b := NewRetryBuffer(2) // tiny cap

	// Fail three windows; only the two newest may remain.
	_ = b.Send(context.Background(), p.send, win(1))
	_ = b.Send(context.Background(), p.send, win(2))
	_ = b.Send(context.Background(), p.send, win(3))

	if b.Len() != 2 {
		t.Fatalf("expected buffer capped at 2, got %d", b.Len())
	}

	// Drain and confirm window 1 (oldest) was evicted, leaving 2 and 3.
	p.fail = false
	if err := b.Send(context.Background(), p.send, win(4)); err != nil {
		t.Fatalf("unexpected error draining: %v", err)
	}
	got := map[time.Time]bool{}
	for _, w := range p.sent {
		got[w.WindowStart] = true
	}
	if got[win(1).WindowStart] {
		t.Error("oldest window (1) should have been evicted but was delivered")
	}
	for _, id := range []int{2, 3, 4} {
		if !got[win(id).WindowStart] {
			t.Errorf("expected window %d to be delivered", id)
		}
	}
}

// TestRetryBuffer_PartialDrainStopsAtFirstFailure verifies that when the API
// is still down mid-drain, the backlog (plus the current window) is retained
// rather than partially lost.
func TestRetryBuffer_PartialDrainStopsAtFirstFailure(t *testing.T) {
	b := NewRetryBuffer(8)

	// Seed two buffered windows via a failing poster.
	failing := &recordingPoster{fail: true}
	_ = b.Send(context.Background(), failing.send, win(1))
	_ = b.Send(context.Background(), failing.send, win(2))

	// A poster that succeeds for the first delivery then fails: the
	// backlog drain should land win(1), fail on win(2), and re-buffer
	// win(2) + the current win(3).
	calls := 0
	flaky := func(_ context.Context, w FlowWindow) error {
		calls++
		if calls == 1 {
			return nil
		}
		return errors.New("down again")
	}
	if err := b.Send(context.Background(), flaky, win(3)); err == nil {
		t.Fatal("expected error when drain fails mid-way")
	}
	if b.Len() != 2 {
		t.Fatalf("expected win(2) + win(3) re-buffered, got %d", b.Len())
	}
}

func TestRetryBuffer_NonPositiveCapClampedToOne(t *testing.T) {
	b := NewRetryBuffer(0)
	p := &recordingPoster{fail: true}
	_ = b.Send(context.Background(), p.send, win(1))
	_ = b.Send(context.Background(), p.send, win(2))
	if b.Len() != 1 {
		t.Fatalf("expected cap clamped to 1, got %d buffered", b.Len())
	}
}
