# Publishing the companion app to Google Play

End-to-end checklist for shipping the Flutter companion to the Play Store. Pick this up on a machine that already has a JDK + Android SDK installed (or run `brew install --cask android-studio` first and let it finish first-launch SDK setup).

Current state of the repo:
- `companion/android/app/build.gradle.kts` already reads release signing from `companion/android/key.properties` (gitignored).
- `applicationId` = `space.elghareeb.beats`.
- `versionName` = 1.0.0, `versionCode` = 1 (from `companion/pubspec.yaml` → `version: 1.0.0+1`).
- App label in `AndroidManifest.xml` is **"Pete"** — confirm this is the public name before uploading. If it should be "Beats", update `android:label` in `companion/android/app/src/main/AndroidManifest.xml` first.

## 1. Generate the upload keystore

One-time. Back the resulting `.jks` up somewhere offline (1Password, encrypted drive) — losing it means you cannot publish updates to this app, ever.

```bash
cd companion
keytool -genkey -v \
  -keystore android/upload-keystore.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias upload
```

Prompts:
- Keystore password (≥6 chars) — save in password manager
- Re-enter password
- First and last name (CN) → `Ahmed Elghareeb`
- OU / O / L / ST → can leave blank
- Two-letter country code → e.g. `EG`
- Confirm `yes`
- Key password for `upload` → press Enter to reuse the keystore password

## 2. Wire `key.properties`

Create `companion/android/key.properties` (already in `.gitignore`):

```properties
storePassword=<keystore password from step 1>
keyPassword=<same password if you reused it>
keyAlias=upload
storeFile=../upload-keystore.jks
```

`storeFile` is resolved relative to `companion/android/app/`, so `../upload-keystore.jks` points at the file created in step 1.

## 3. Build the app bundle

```bash
cd companion
flutter pub get
flutter build appbundle --release
```

Output: `companion/build/app/outputs/bundle/release/app-release.aab`

Sanity-check that release signing actually kicked in (no debug-signed bundle):

```bash
unzip -p build/app/outputs/bundle/release/app-release.aab META-INF/MANIFEST.MF | head
```

The build script in `android/app/build.gradle.kts` fails loudly if `key.properties` is missing, so a successful `flutter build appbundle --release` is itself confirmation.

## 4. Pre-flight before uploading

Things Play Console will require that need to be ready:

- [ ] **Privacy policy URL** — publicly hosted. The repo has `PRIVACY.md` and `DATA.md` on the homepage; make sure they're live at a stable URL.
- [ ] **App icon** — high-res 512×512 PNG for the store listing (the launcher icon at `mipmap/ic_launcher` is for the device only).
- [ ] **Feature graphic** — 1024×500 PNG for the store listing.
- [ ] **Screenshots** — at least 2 phone screenshots (1080×1920 or similar).
- [ ] **Short description** (80 chars) and **full description** (4000 chars).
- [ ] **Content rating** questionnaire (in-app).
- [ ] **Data Safety form** — declare what's collected and why. The app sends biometrics, productivity sessions, and integrates with health providers. Be specific.
- [ ] **Target audience and content** — age groups, ads (none), etc.
- [ ] **Permissions justification** for:
  - `POST_NOTIFICATIONS` — drift alerts, EOD prompt
  - `SCHEDULE_EXACT_ALARM` — exact EOD scheduling during Doze
  - `RECEIVE_BOOT_COMPLETED` — re-arm scheduled notifications after reboot
  - `CAMERA` — QR pairing on the PairingScreen
- [ ] **Health Connect declaration** — Health Connect integration triggers an extra Play Console form ("Health app declaration") plus typically a demo video walking through how each health data type is used. Plan for this; review can take a few days.

## 5. Play Console upload flow

1. Create app:
   - Default language, app or game = App, free, accept declarations.
   - Package name `space.elghareeb.beats`.
2. Set up the **Internal testing** track first — review is fast, and you can install via an opt-in link on your own device before promoting.
3. Upload `app-release.aab` to the internal track.
4. Fill the store listing, Data Safety, content rating, target audience.
5. Submit for internal review. When approved, copy the opt-in URL to your phone and install via Play.
6. Promote to **Closed testing** (a handful of testers) → **Open testing** (anyone with the link) → **Production** as confidence grows.

## 6. Subsequent releases

For each new release:
- Bump `version:` in `companion/pubspec.yaml` (both the name and the `+N` build number — Play rejects duplicates).
- `flutter build appbundle --release`
- Upload the new `.aab` to the relevant track in Play Console.

The keystore from step 1 stays the same forever. The `.aab` and `versionCode` change each release.

## Open decisions to make before publishing

- App label: keep **"Pete"** or change to **"Beats"** in `AndroidManifest.xml`?
- Privacy policy URL: where will `PRIVACY.md` and `DATA.md` be publicly hosted?
- Initial release track: ship straight to production after internal smoke, or go through closed/open testing first?
