// Package pair handles the daemon-to-API pairing flow and keychain storage.
package pair

import (
	"context"
	"fmt"

	"github.com/zalando/go-keyring"

	"github.com/ahmedElghable/beats/daemon/internal/client"
)

const (
	keychainService = "beats-daemon"
	keychainAccount = "device-token"
)

// Run executes the pairing flow:
//  1. Exchanges the pairing code for a device token via the API
//  2. Stores the token in the OS keychain
func Run(ctx context.Context, c *client.Client, code string, deviceName string) (string, error) {
	resp, err := c.ExchangePairCode(ctx, code, deviceName)
	if err != nil {
		return "", fmt.Errorf("pair exchange failed: %w", err)
	}

	if err := StoreToken(resp.DeviceToken); err != nil {
		return "", fmt.Errorf("store token in keychain: %w", err)
	}

	return resp.DeviceID, nil
}

// LoadToken retrieves the device token from the OS keychain.
// Returns ("", nil) if no token is stored (not yet paired).
func LoadToken() (string, error) {
	token, err := keyring.Get(keychainService, keychainAccount)
	if err != nil {
		if err == keyring.ErrNotFound {
			return "", nil
		}
		return "", fmt.Errorf("read keychain: %w", err)
	}
	return token, nil
}

// StoreToken saves the device token to the OS keychain.
func StoreToken(token string) error {
	return keyring.Set(keychainService, keychainAccount, token)
}

// DeleteToken removes the device token from the OS keychain.
func DeleteToken() error {
	err := keyring.Delete(keychainService, keychainAccount)
	if err != nil && err != keyring.ErrNotFound {
		return err
	}
	return nil
}
