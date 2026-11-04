package client

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// The refusal gate is what keeps a suspended account's daemon from
// hammering the API and what lets it notice, on its own, that the
// suspension lifted. Pin the probe arithmetic and that only the two
// standing refusals close it — an ordinary 500 must keep today's
// retry behaviour.

func refusalErr(code string) error {
	return &APIError{Op: "post", StatusCode: 403, Code: code, detail: "refused"}
}

func gateAt(clock *time.Time) *RefusalGate {
	g := NewRefusalGate(10 * time.Minute)
	g.now = func() time.Time { return *clock }
	return g
}

func TestRefusalGate_OpenGateBlocksNothing(t *testing.T) {
	clock := time.Unix(1000, 0)
	g := gateAt(&clock)
	for i := 0; i < 3; i++ {
		if g.Blocked() {
			t.Fatal("open gate must not block")
		}
	}
	if g.Refusal() != "" {
		t.Fatalf("open gate reports refusal %q", g.Refusal())
	}
}

func TestRefusalGate_ClosesOnRefusalOnceAndProbesPerInterval(t *testing.T) {
	clock := time.Unix(1000, 0)
	g := gateAt(&clock)

	if !g.Note(refusalErr(CodeAccountSuspended)) {
		t.Fatal("first refusal must report newly refused (it is logged once)")
	}
	if g.Note(refusalErr(CodeAccountSuspended)) {
		t.Fatal("repeating the same refusal must stay silent")
	}
	if g.Refusal() != CodeAccountSuspended {
		t.Fatalf("refusal = %q", g.Refusal())
	}

	if !g.Blocked() {
		t.Fatal("refused gate must block before the interval")
	}
	clock = clock.Add(10*time.Minute + time.Second)
	if g.Blocked() {
		t.Fatal("the first call past the interval is the probe")
	}
	if !g.Blocked() {
		t.Fatal("the probe is one call; the next must block again")
	}
}

func TestRefusalGate_IgnoresOrdinaryFailures(t *testing.T) {
	clock := time.Unix(1000, 0)
	g := gateAt(&clock)

	if g.Note(&APIError{Op: "post", StatusCode: 500, Code: "INTERNAL_ERROR"}) {
		t.Fatal("a 500 is not a standing refusal")
	}
	if g.Note(errors.New("dial tcp: connection refused")) {
		t.Fatal("a network error is not a standing refusal")
	}
	if g.Blocked() {
		t.Fatal("gate must stay open")
	}
}

func TestRefusalGate_ClearReopensAndReportsOnce(t *testing.T) {
	clock := time.Unix(1000, 0)
	g := gateAt(&clock)
	g.Note(refusalErr(CodeDeviceRevoked))

	if !g.Clear() {
		t.Fatal("clearing a refused gate reports the recovery (logged once)")
	}
	if g.Clear() {
		t.Fatal("clearing an open gate must stay silent")
	}
	if g.Blocked() {
		t.Fatal("cleared gate must not block")
	}
}

func TestRefusalGate_ANewRefusalKindIsLoggedAgain(t *testing.T) {
	clock := time.Unix(1000, 0)
	g := gateAt(&clock)
	g.Note(refusalErr(CodeAccountSuspended))
	if !g.Note(refusalErr(CodeDeviceRevoked)) {
		t.Fatal("a different refusal is new information and is logged")
	}
}

func TestErrorCode_ReadsTheEnvelopeOffARealResponse(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte(`{"detail": "This account is suspended.", "code": "ACCOUNT_SUSPENDED"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	err := c.PostHeartbeat(context.Background())
	if err == nil {
		t.Fatal("expected an error")
	}
	if ErrorCode(err) != CodeAccountSuspended {
		t.Fatalf("ErrorCode = %q", ErrorCode(err))
	}
	// The rendered message is unchanged from before the typed error: the
	// detail and the code a person reads in the log stayed put.
	want := `request to /api/device/heartbeat failed (HTTP 403): ` +
		`This account is suspended. [ACCOUNT_SUSPENDED]`
	if err.Error() != want {
		t.Fatalf("error text changed:\n got %q\nwant %q", err.Error(), want)
	}
}

func TestErrorCode_EmptyForOtherErrors(t *testing.T) {
	if ErrorCode(nil) != "" {
		t.Fatal("nil has no code")
	}
	if ErrorCode(errors.New("boom")) != "" {
		t.Fatal("a plain error has no code")
	}
}

func TestRefusalWord(t *testing.T) {
	if RefusalWord(CodeAccountSuspended) != "account suspended" {
		t.Fatal("account wording")
	}
	if RefusalWord(CodeDeviceRevoked) != "device revoked" {
		t.Fatal("device wording")
	}
	if RefusalWord("OTHER") != "OTHER" {
		t.Fatal("unknown codes pass through")
	}
}
