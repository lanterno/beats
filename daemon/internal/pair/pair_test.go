package pair

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/zalando/go-keyring"

	"github.com/ahmedElghable/beats/daemon/internal/client"
)

func init() {
	// Use mock keyring in tests (in-memory, no OS integration)
	keyring.MockInit()
}

func TestRunSuccess(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{
			"device_token": "tok_test_123",
			"device_id":    "dev-test-uuid",
		})
	}))
	defer srv.Close()

	c := client.New(srv.URL, "")
	deviceID, err := Run(context.Background(), c, "ABC123", "test-host")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if deviceID != "dev-test-uuid" {
		t.Errorf("expected device ID dev-test-uuid, got %s", deviceID)
	}

	// Verify token was stored
	token, err := LoadToken()
	if err != nil {
		t.Fatalf("unexpected error loading token: %v", err)
	}
	if token != "tok_test_123" {
		t.Errorf("expected stored token tok_test_123, got %s", token)
	}
}

func TestRunExchangeFailure(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte(`{"detail":"Invalid code"}`))
	}))
	defer srv.Close()

	c := client.New(srv.URL, "")
	_, err := Run(context.Background(), c, "BADCOD", "test-host")
	if err == nil {
		t.Fatal("expected error for failed exchange")
	}
}

func TestLoadTokenNotPaired(t *testing.T) {
	// Clean up any token from previous tests
	_ = DeleteToken()

	token, err := LoadToken()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if token != "" {
		t.Errorf("expected empty token for unpaired device, got %s", token)
	}
}

func TestStoreAndDeleteToken(t *testing.T) {
	if err := StoreToken("test-token-456"); err != nil {
		t.Fatalf("store failed: %v", err)
	}

	token, err := LoadToken()
	if err != nil {
		t.Fatalf("load failed: %v", err)
	}
	if token != "test-token-456" {
		t.Errorf("expected test-token-456, got %s", token)
	}

	if err := DeleteToken(); err != nil {
		t.Fatalf("delete failed: %v", err)
	}

	token, err = LoadToken()
	if err != nil {
		t.Fatalf("load after delete failed: %v", err)
	}
	if token != "" {
		t.Errorf("expected empty token after delete, got %s", token)
	}
}
