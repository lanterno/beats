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

Publish a GitHub release whose tag is `companion-v<version>`:

```bash
gh release create companion-v1.1.0 --generate-notes                     # → the closed test
gh release create companion-v1.1.0-rc.1 --prerelease --generate-notes   # → internal testing
```

(or *Releases → Draft a new release* on GitHub). **Release Android** then tests,
builds the bundle signed with the upload key, checks the native libraries are
16 KB-aligned, attaches `lifepete-<version>-<code>.aab` to the release, and
uploads it to Google Play with the release notes as *What's new*:

- A **pre-release** goes to **internal testing**.
- A **full release** goes to the track in the repo variable `PLAY_RELEASE_TRACK`:
  `alpha` (the closed test) today, `production` once production access is
  granted (`gh variable set PLAY_RELEASE_TRACK -R lanterno/beats --body production`).
  Unset, a full release fails instead of guessing.

The upload is a completed release on that track. With managed publishing off,
Google reviews it and it goes out on approval; to hold a production rollout or
stage it, use the console. `versionCode` is the workflow's run number,
`versionName` the tag without `companion-v`. *What's new* is the notes as plain
text, cut to Play's 500 characters (`android/play_notes.py`): the generated
notes' "by @someone in <PR>" and "Full Changelog" lines are dropped, so write the
title of each PR for someone reading it on a phone.

Run by hand from the Actions tab, the workflow only builds and keeps the bundle
as an artifact.

**Play access** is `play-publisher@beats-476914.iam.gserviceaccount.com`, a
service account with no Cloud roles. In Play Console → *Users and permissions*
it has LifePete only: release to testing tracks and to production (which brings
policy declarations and deep links with it). Its JSON key is
`play.service_account_json` in the vault, sent to Actions as
`PLAY_SERVICE_ACCOUNT_JSON` by `vault gh beats`. A leaked key alone can't ship a
build: Play also needs the upload key's signature. To rotate it, create a new key
(`gcloud iam service-accounts keys create`) into `vault set beats
play.service_account_json -`, run `vault gh beats`, then delete the old key.

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
   Paste the text files (the title is the app name), upload the images (the
   screenshots in their numbered order), and answer the AI asset declaration
   *Don't label assets* (they are renders of the app and hand-drawn SVG).
   *Store settings*: category Productivity; contact email
   ahmed.elghareeb@proton.me; website https://lifepete.com.
6. **Closed testing.** Create a closed track, add testers by email or a Google
   Group, share the opt-in link, and promote the internal build to it.
7. **Production access.** After 14 days with 12 or more testers, *Dashboard →
   Apply for production*, answer the questions about the test, then create a
   production release from the same bundle and send it for review.
8. **Automated uploads** are set up: see *Releasing a build* above.

## App content answers

**Privacy policy** — https://github.com/lanterno/beats/blob/main/PRIVACY.md

**Sign in details** (formerly App access) — *Yes, part of the app is
restricted*. One set of details, named "Sample data (no account needed)", no
username or password, with these instructions (it must stay under 500
characters), and *full access* ticked:

> No account is needed to review. On the first screen (Pair this device), tap
> "No account yet? Look around with sample data" at the bottom. Every screen
> then works on made-up data: start, stop and switch the timer (the gold +
> button), Today, Flow, Coach (chat replies), Body, Settings and Focus mode.
> Pairing a real account needs a code from lifepete.com, which review doesn't
> need.

**Ads** — No.

**Content rating** — questionnaire category *All other app types*. *Online
content: Yes* — the coach's replies are generated AI content that isn't in the
download. Everything else No: no violence, sexuality, language, drugs or
age-restricted products; users don't interact with each other; no location
sharing, digital purchases, rewards, browser or news. Rated all ages.

**Target audience** — 18 and over. It isn't made for children, and saying so
keeps the Families policy out of scope.

**News app** — No. **Government app** — No. **Financial features** — None.
**Advertising ID** — No: the merged manifest has no
`com.google.android.gms.permission.AD_ID` (check the bundle again after adding
a Google SDK).

**Health apps** — *Activity and fitness* and *Sleep management*: the app shows
sleep, HRV, resting heart rate and steps that the person connected from Oura
or Fitbit on their account. It doesn't read the phone's health stores, and
nothing medical is ticked.

**Data safety.** "Collected" means it leaves the phone; data the app only
shows from the person's own server isn't collected by the app.

- Does the app collect or share user data? **Yes** (collects; does not share).
- Encrypted in transit? **Yes** — HTTPS to lifepete.com. (Someone pointing the
  app at their own server chooses its scheme.)
- Account creation: *My app does not allow users to create an account*, but
  *users can log in with accounts created outside the app* → *Other*: "On the
  LifePete website (lifepete.com) with an email and a passkey; the app is then
  paired with a one-time code."
- Data deletion: **Yes**, at
  https://github.com/lanterno/beats/blob/main/PRIVACY.md#export-and-deletion
  (by email, as that section says).
- Data types, all *collected*, *not shared*, *not ephemeral*:
  - **Messages → Other in-app messages** — coach chat. *Optional* (nobody has
    to chat), for *App functionality*. The API passes it to Anthropic to
    answer, which is a service provider acting for us, so not "shared".
  - **App activity → Other user-generated content** — sessions logged, project
    choices, brief ratings. *Required*, *App functionality*.
  - **App activity → Other actions** — starting, stopping and switching the
    timer. *Required*, *App functionality*.
  - **Device or other IDs** — the device name sent when pairing. *Required*,
    *App functionality* and *Analytics* (the scanner's installation ID, below).
- The code scanner adds two more. `mobile_scanner` 7.2 pulls in Google ML Kit's
  bundled barcode model (`com.google.mlkit:barcode-scanning:17.3.0`; nothing
  sets `useUnbundled`), and ML Kit sends Google usage diagnostics: device and
  app info, performance metrics, error codes, and a per-installation ID that
  isn't meant to identify the person or the phone
  ([ML Kit's disclosure](https://developers.google.com/ml-kit/android-data-disclosure)).
  ML Kit says it doesn't pass this to third parties. Both *collected*, *not
  shared*, *required*, for *Analytics*:
  - **App info and performance → Diagnostics**
  - **Device or other IDs** (already above, with *Analytics* among its purposes)

  Switching scanner versions, or to the unbundled model, changes this list;
  check the disclosure page again when you do.

## Remaking the images

```bash
companion/store/render.sh            # icon, feature graphic, screenshots
companion/store/render.sh graphic    # just one: icon | graphic | screenshots
```

Screenshots run the Mac debug build at 540×960 on sample data with no
banner (`LIFEPETE_PHONE=store`, `LIFEPETE_SAMPLE=quiet`), so they never show a
real account. They need an unlocked screen.
