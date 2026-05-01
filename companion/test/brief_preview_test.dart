// Tests for briefPreview — the pure brief-body → notification-preview
// transformation extracted from NotificationPoller. Locks in the
// rules that actually matter for what shows up in macOS / iOS
// notifications.

import 'package:beats_companion/services/notification_poller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('briefPreview', () {
    test('returns null for null input', () {
      expect(briefPreview(null), isNull);
    });

    test('returns null for empty string', () {
      expect(briefPreview(''), isNull);
    });

    test('returns null for whitespace-only string', () {
      // After collapse + trim, "   \n\t  " becomes "" — should be
      // null, not an empty preview that renders as a hollow notif.
      expect(briefPreview('   \n\t  '), isNull);
    });

    test('returns short bodies unchanged', () {
      expect(briefPreview('You have 3 intentions today.'),
          'You have 3 intentions today.');
    });

    test('collapses internal whitespace runs to a single space', () {
      // Briefs come back as multi-line markdown-ish prose. A
      // notification with embedded \n looks broken on macOS.
      expect(
        briefPreview('Line one.\nLine two.\n\n  Line three with  extra  spaces.'),
        'Line one. Line two. Line three with extra spaces.',
      );
    });

    test('trims leading and trailing whitespace after collapse', () {
      expect(briefPreview('  hello  '), 'hello');
    });

    test('truncates to 80 chars and appends ellipsis when over', () {
      final long = 'x' * 200;
      final preview = briefPreview(long);
      expect(preview, isNotNull);
      // 80 'x' chars + '…' = 81 visible characters. We don't reserve
      // a slot for the ellipsis — the cap-then-ellipsis pattern
      // matches what the user sees in their notification feed.
      expect(preview!.length, 81);
      expect(preview.endsWith('…'), isTrue);
      expect(preview.substring(0, 80), 'x' * 80);
    });

    test('does not append ellipsis on bodies exactly 80 chars', () {
      // Exactly 80 chars passes through unchanged — > is the
      // truncation predicate, not >=. Locks that boundary in so a
      // refactor to >= doesn't quietly clip an 80-char body.
      final exactly = 'a' * 80;
      expect(briefPreview(exactly), exactly);
    });

    test('counts code-point length, not byte length, for the truncation', () {
      // Multi-byte UTF-8 characters (em-dash, emoji, accented chars)
      // are 1 code point each. The runtime String.length in Dart is
      // UTF-16 code units, so single-codepoint emoji like 😀 (U+1F600)
      // count as 2 — but standard accented chars like é are 1.
      // Lock in current behavior: the 80-char window is in code
      // units, NOT graphemes. A future grapheme-aware refactor
      // would change this and we'd want to know.
      final accented = 'é' * 100; // 100 code units, all single-byte-ish
      final preview = briefPreview(accented);
      expect(preview!.length, 81); // 80 accented + ellipsis
    });
  });
}
