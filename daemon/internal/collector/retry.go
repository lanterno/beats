package collector

import "context"

// FlowPoster sends a single flow window to the API. It mirrors the
// signature of client.Client.PostFlowWindow once a FlowWindow is mapped
// to the request body, but is kept as a plain func so the retry buffer
// has no dependency on the client package (and is trivially fakeable in
// tests).
type FlowPoster func(ctx context.Context, w FlowWindow) error

// RetryBuffer is a small BOUNDED in-memory queue of flow windows that
// failed to POST. The collector loses its core metric whenever a window
// is dropped, so a brief network blip shouldn't be permanent: we keep the
// failed window around and retry it on the next flush.
//
// It is intentionally simple and NOT goroutine-safe — the collector loop
// invokes the onWindow callback synchronously on a single goroutine, so
// all access is serialized there. The cap keeps memory bounded; when the
// buffer is full the OLDEST pending window is evicted to make room (a
// fresh window is more valuable than a stale one we've already failed to
// deliver repeatedly).
type RetryBuffer struct {
	pending []FlowWindow
	cap     int
}

// NewRetryBuffer returns a buffer that holds at most cap pending windows.
// A non-positive cap is clamped to 1 so the buffer always retains at
// least the most recent failure.
func NewRetryBuffer(cap int) *RetryBuffer {
	if cap < 1 {
		cap = 1
	}
	return &RetryBuffer{cap: cap}
}

// Len reports how many windows are currently buffered for retry.
func (b *RetryBuffer) Len() int { return len(b.pending) }

// enqueue appends w, evicting the oldest entry first if the buffer is at
// capacity so memory stays bounded.
func (b *RetryBuffer) enqueue(w FlowWindow) {
	if len(b.pending) >= b.cap {
		// Drop oldest: shift the slice window forward by one.
		b.pending = b.pending[1:]
	}
	b.pending = append(b.pending, w)
}

// Send posts w via poster. On success it first drains any previously
// buffered windows (oldest first), then sends w. On any failure the
// offending window is enqueued for a later retry and Send returns the
// error so the caller can log / count it.
//
// Draining stops at the first failure: if the API is still unreachable
// there's no point hammering it with the whole backlog, and the
// remaining (plus the current) windows stay buffered for next time.
func (b *RetryBuffer) Send(ctx context.Context, poster FlowPoster, w FlowWindow) error {
	// Try to flush the backlog first so windows land in chronological
	// order. Anything that fails is re-buffered below.
	backlog := b.pending
	b.pending = nil
	for i, pw := range backlog {
		if err := poster(ctx, pw); err != nil {
			// Re-buffer the failed window plus everything after it
			// (still undelivered), then enqueue the current window so
			// it isn't lost either, and report the failure.
			for _, rem := range backlog[i:] {
				b.enqueue(rem)
			}
			b.enqueue(w)
			return err
		}
	}

	// Backlog drained; now send the current window.
	if err := poster(ctx, w); err != nil {
		b.enqueue(w)
		return err
	}
	return nil
}
