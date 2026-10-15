# Google Play

Everything the Play Console asks for, and where it comes from. The listing's
text and images live in `android/en-US/` (fastlane's layout, so a tool can
upload them later); `render.sh` remakes the images.

| What | Where |
|---|---|
| Package name | `space.elghareeb.beats` (permanent once the first bundle is uploaded) |
| App name | LifePete |
| Title, short and full description | `android/en-US/title.txt`, `short_description.txt`, `full_description.txt` |
| Icon, 512×512 | `android/en-US/images/icon.png` — `shared/brand/maskable.svg`; Play rounds the corners |
| Feature graphic, 1024×500 | `android/en-US/images/featureGraphic.png` — `feature-graphic.html` |
| Phone screenshots, 1080×1920 | `android/en-US/images/phoneScreenshots/` — the app on sample data |
| Privacy policy | https://github.com/lanterno/beats/blob/main/PRIVACY.md |
| Signed bundle | the **Release Android** workflow (`.github/workflows/release-android.yml`) |
| Upload key | repo secrets `ANDROID_UPLOAD_KEYSTORE_BASE64` / `_PASSWORD`, set from the maintainer's vault (`vault gh beats`; the keystore is `vault get-file beats android-upload-keystore`) |

## Releasing a build

Tag it, or run **Release Android** from the Actions tab:

```bash
git tag companion-v1.0.0 && git push origin companion-v1.0.0
```

The workflow tests, builds the bundle signed with the upload key, checks the
native libraries are 16 KB-aligned, and keeps `lifepete-<version>-<code>.aab`
as an artifact (and on the GitHub release, for a tag). `versionCode` is the
run number. With `PLAY_SERVICE_ACCOUNT_JSON` set it also uploads to the
internal testing track as a draft.

## First publication, step by step

These need the account holder; the rest is done.

1. **Developer account.** https://play.google.com/console/signup — a personal
   account, the one-off fee, identity verification and a verified phone. A
   personal account made after November 2023 must run a closed test with at
   least 12 testers opted in for 14 days in a row before it can apply for
   production (step 7), so start inviting people early.
2. **Create the app.** Name LifePete, default language English (United States),
   App, Free. Accept the Developer Program Policies and US export laws.
3. **First bundle.** Run Release Android and download the artifact. Upload it
   by hand in *Test and release → Testing → Internal testing → Create new
   release*: the API can only add to an app that already has a bundle. When
   asked, let Google manage the app signing key (Play App Signing); ours is
   only the upload key. Add yourself as an internal tester and install it.
4. **App content** (*Policy and programs → App content*). Answers below.
5. **Store listing** (*Grow users → Store presence → Main store listing*).
   Paste the text files, upload the images. Category Productivity; contact
   email ahmed.elghareeb@proton.me; website https://lifepete.com.
6. **Closed testing.** Create a closed track, add testers by email or a Google
   Group, share the opt-in link, and promote the internal build to it.
7. **Production access.** After 14 days with 12 or more testers, *Dashboard →
   Apply for production*, answer the questions about the test, then create a
   production release from the same bundle and send it for review.
8. **Automate uploads (optional).** Google Cloud → a service account with a
   JSON key → invite it in *Users and permissions* with release rights →
   save the JSON as the `PLAY_SERVICE_ACCOUNT_JSON` repo secret.

## App content answers

**Privacy policy** — https://github.com/lanterno/beats/blob/main/PRIVACY.md

**App access** — *All or some functionality is restricted*. Add instructions,
no credentials:

> LifePete shows a person's own time-tracking account, which needs pairing
> with lifepete.com. To review without an account, on the first screen tap
> "No account yet? Look around with sample data". Every screen then works on
> made-up data: start, stop and switch the timer (the gold + button), Flow,
> Coach (the chat replies), Body, Settings and Focus mode.

**Ads** — No.

**Content rating** — questionnaire category *All other app types*. No violence,
sexuality, language, drugs or gambling. Users don't interact with each other
or share content; there is no purchase. The coach is an AI chat that answers
from the person's own data. Expect *Everyone* / PEGI 3.

**Target audience** — 18 and over. It isn't made for children, and saying so
keeps the Families policy out of scope.

**News app** — No. **Government app** — No. **Financial features** — None.

**Health apps** — the app shows sleep, HRV, resting heart rate and steps that
the person connected from Oura or Fitbit on their account; it doesn't read
the phone's health stores. If the form asks, it is a *fitness and wellness*
display, not a medical or diagnostic feature.

**Data safety.** "Collected" means it leaves the phone; data the app only
shows from the person's own server isn't collected by the app.

- Does the app collect or share user data? **Yes** (collects; does not share).
- Encrypted in transit? **Yes** — HTTPS to lifepete.com. (Someone pointing the
  app at their own server chooses its scheme.)
- Can users ask for their data to be deleted? **Yes** — by email, as
  PRIVACY.md says.
- Data types, all *collected*, *not shared*, *required* (the app is a client
  of the account), for *App functionality*:
  - **App activity → Other user-generated content** — sessions logged, project
    choices, brief ratings, coach chat messages.
  - **App activity → Other actions** — starting, stopping and switching the timer.
  - **Device or other IDs** — the device name sent when pairing.
- **Check before submitting:** Google ML Kit (the code scanner, via
  `mobile_scanner`) may collect diagnostics. Look it up in the Google Play SDK
  Index (play.google.com/sdks) for the version in the bundle, and add what it
  lists — likely *App info and performance → Diagnostics* and *Device or other
  IDs*, collected for analytics, by Google.

## Remaking the images

```bash
companion/store/render.sh            # icon, feature graphic, screenshots
companion/store/render.sh graphic    # just one: icon | graphic | screenshots
```

Screenshots run the Mac debug build at 540×960 on sample data with no
banner (`LIFEPETE_PHONE=store`, `LIFEPETE_SAMPLE=quiet`), so they never show a
real account. They need an unlocked screen.
