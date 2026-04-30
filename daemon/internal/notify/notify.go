// Package notify shows native desktop notifications across darwin, linux,
// and windows. Best-effort: failures are logged but never propagated, since
// these calls live on hot paths (drift detection, autotimer suggestions)
// where a missing notification beats a crashed daemon.
package notify

import (
	"fmt"
	"log"
	"os/exec"
	"runtime"
)

// Send shows a notification with the given title and body. Returns nothing
// because every callsite is best-effort — the daemon should never block or
// surface an error to the user because notify-send was missing.
func Send(title, body string) {
	switch runtime.GOOS {
	case "darwin":
		sendDarwin(title, body)
	case "linux":
		sendLinux(title, body)
	case "windows":
		sendWindows(title, body)
	default:
		log.Printf("notify: %s — %s (no native delivery on %s)", title, body, runtime.GOOS)
	}
}

func sendDarwin(title, body string) {
	// osascript is everywhere on macOS; the notification appears under
	// "Script Editor" because we don't sign with a custom bundle. A future
	// improvement is a tiny ObjC wrapper via cgo using
	// UNUserNotificationCenter, but that needs a signed binary.
	script := fmt.Sprintf(`display notification %q with title %q`, body, title)
	if err := exec.Command("osascript", "-e", script).Run(); err != nil {
		log.Printf("notify: osascript failed: %v", err)
	}
}

func sendLinux(title, body string) {
	// `notify-send` ships with libnotify-bin on Debian/Ubuntu and is the
	// de-facto standard across the major desktops. If it's missing we just
	// log; the user can `apt install libnotify-bin` to wire it up.
	if _, err := exec.LookPath("notify-send"); err != nil {
		log.Printf("notify: %s — %s (install libnotify-bin for native delivery)", title, body)
		return
	}
	if err := exec.Command("notify-send", "--app-name=beats", title, body).Run(); err != nil {
		log.Printf("notify: notify-send failed: %v", err)
	}
}

func sendWindows(title, body string) {
	// Windows 10/11 toast notifications via PowerShell. The XML literal is
	// the documented schema for ToastGeneric. Single-quoting and replacing
	// embedded apostrophes keeps PowerShell out of trouble; we don't
	// expect adversarial input here (titles/bodies come from the daemon).
	escapedTitle := psEscape(title)
	escapedBody := psEscape(body)
	script := fmt.Sprintf(`
$xml = '<toast><visual><binding template="ToastGeneric"><text>%s</text><text>%s</text></binding></visual></toast>'
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
$toast = New-Object Windows.UI.Notifications.ToastNotification $doc
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('beats').Show($toast)
`, escapedTitle, escapedBody)
	if err := exec.Command("powershell", "-NoProfile", "-Command", script).Run(); err != nil {
		log.Printf("notify: powershell toast failed: %v", err)
	}
}

func psEscape(s string) string {
	out := make([]rune, 0, len(s))
	for _, r := range s {
		if r == '\'' {
			out = append(out, '\'', '\'')
			continue
		}
		out = append(out, r)
	}
	return string(out)
}
