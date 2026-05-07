// Tests for driftAppLabel — the bundle-id → human-readable-app-name
// helper used by the drift notification body. Pure: extracted from
// NotificationPoller so the well-known-bundles table can grow with
// confidence and the fallback formatting is locked in.

import 'package:beats_companion/services/notification_poller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('driftAppLabel — known bundles', () {
    test('returns the curated label for a known macOS bundle', () {
      // Lock in a few bundles the daemon's drift list explicitly knows
      // about — these are the apps the shield is most likely to flag,
      // so getting their notification body right matters most.
      expect(driftAppLabel('com.twitter.twitter-mac'), 'Twitter');
      expect(driftAppLabel('com.spotify.client'), 'Spotify');
      expect(driftAppLabel('com.hnc.discord'), 'Discord');
      expect(driftAppLabel('com.tinyspeck.slackmacgap'), 'Slack');
    });

    test('treats the legacy Tweetie bundle as Twitter too', () {
      // Older Twitter Mac client used a different reverse-DNS bundle id
      // before the Twitter rebrand. Same product, same notification copy.
      expect(driftAppLabel('com.atebits.tweetie2'), 'Twitter');
    });
  });

  group('driftAppLabel — fallback', () {
    test('takes the last dotted segment for unknown bundles', () {
      // Unknown bundle: fall back to the last dotted segment so the
      // notification reads as something rather than an opaque
      // reverse-DNS string the user has to mentally translate.
      expect(driftAppLabel('com.unknownco.coolapp'), 'Coolapp');
    });

    test('replaces dashes and underscores with spaces in the segment', () {
      // "twitter-mac" → "Twitter Mac"; "my_app_name" → "My App Name".
      // Locks in the rule so a future refactor that strips separators
      // entirely (and produces "twittermac") gets caught.
      expect(driftAppLabel('com.example.twitter-mac'), 'Twitter Mac');
      expect(driftAppLabel('com.example.my_app_name'), 'My App Name');
    });

    test('title-cases each word', () {
      expect(driftAppLabel('com.example.lower-case-words'), 'Lower Case Words');
      // Already-uppercase letters get downcased except the first.
      expect(driftAppLabel('com.example.SHOUTY'), 'Shouty');
    });

    test('returns the raw bundle when the last segment is empty', () {
      // "com.example." has an empty last segment; rather than producing
      // the empty string, fall back to the input so the notification
      // still says something locatable.
      expect(driftAppLabel('com.example.'), 'com.example.');
    });
  });

  group('driftAppLabel — edge cases', () {
    test('returns "an app" for empty input', () {
      // Drift events from the API should always carry a non-empty
      // bundle_id, but if one slips through, "an app" still produces
      // a readable notification body ("You\'ve been on an app for…").
      expect(driftAppLabel(''), 'an app');
    });

    test('handles a bundle id with no dots', () {
      // Defensive: an unusual bundle id like just "spotify" still
      // produces a title-cased label.
      expect(driftAppLabel('spotify'), 'Spotify');
    });
  });
}
