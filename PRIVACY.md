# Privacy

This is a personal, open-source project. I (Ahmed Elghareeb, [@lanterno](https://github.com/lanterno)) am the only operator. This page describes — in plain English — what Beats does with your data. Beats is the project's name in code; you meet it as **LifePete** — lifepete.com, the LifePete apps for Mac, Android and iPhone, and the daemon and editor extension that feed them. This policy covers all of them.

For the catalogue of every field stored, see [DATA.md](./DATA.md).

## What Beats is

Beats is a self-tracking system. It records what you work on, for how long, and (optionally) how you felt while doing it. It is not a productivity app sold to employers, and there is no analytics product built on top of your data.

If you mark a project as a day job, Beats also stores its contract — the hours owed each week as a percentage of a full-time basis, the dates those terms changed, an opening balance — the employer's holiday region as two ISO codes, the employer's own days off where they differ from that region's (dates, with the names you give them, and the region's holidays the employer does not give), and the days you were absent (vacation, sick or other, whole or half), and any dated adjustments you make to the balance (a payout, a reset or a cap, with a note if you give one). From those it works out what the week expects of you and a running overtime balance.

## Who can see your data

- **You.** Through the web app, the daemon, the editor extension, the companion app, and the export endpoint.
- **Me, the operator.** I can read any document in the database. I do not log into your account or read your sessions without a reason, but I am not going to pretend a single-operator service has a privileged-access boundary it does not have. If you would not be comfortable with me being able to see something, do not put it in Beats.
- **The hosting providers** that run the infrastructure (Google Cloud for the API, MongoDB Atlas / GCP for the database, Firebase Hosting for the web app). They see encrypted-at-transit traffic and storage they manage on their side. Standard cloud-provider terms apply.
- **No one else.** Beats does not sell, share, or syndicate your data. There are no advertising partners. There is no analytics provider with PII.

## Authentication

Beats uses [WebAuthn passkeys](https://www.w3.org/TR/webauthn-2/). The server never sees a password — it only stores a public key and a counter. Sessions are signed JWTs.

## Third-party integrations (all optional)

If you connect any of these, the relevant OAuth token is stored in the database and used only to fetch the data that integration is for:

- **GitHub** — read commit and repo activity to enrich beats
- **Google Calendar** — read events to align beats with meetings
- **Fitbit, Oura** — read biometric data (sleep, HRV, steps)

The phone apps do not read Apple Health or Health Connect today. If they ever do, it will be opt-in, and this page will say so before the release that adds it.

You can disconnect any integration at any time. Disconnecting revokes the token on Beats' side; revoke at the provider too if you want belt-and-braces.

## The phone apps

The LifePete app on Android and iPhone is a window onto your account; it keeps almost nothing of its own.

- **What it stores on the phone**: the device token from pairing (in Android's Keystore or the iOS Keychain), the server's address, your recent projects and a few settings (light or dusk, which notifications you want). Unpairing deletes the token.
- **What it sends**: requests to your LifePete server — the timer, sessions you log, brief ratings, coach chat — the same as the web app. Pairing sends the phone's name so you can tell devices apart in Settings.
- **Camera**: used only to scan the pairing code, on the phone. No image is stored or sent anywhere.
- **Notifications**: the morning brief, nudges and suggestions, built from your own data while the app is open. No push service is involved.
- **Google libraries**: the code scanner is Google's ML Kit, which runs on the phone and sends Google diagnostics about the scanner itself (device model, OS version, how it performed, under a random ID for this installation that names neither you nor the phone) — never the camera image or anything from your account. The app's two typefaces are fetched from Google Fonts the first time it opens, which shows Google the phone's IP address, as any web page using those fonts does.
- **Sample data**: "Look around with sample data" is made up on the phone and sends nothing.
- **No analytics, no ads, no crash reporting** services are built in.

## The coach

The coach feature sends prompts to the [Anthropic Claude API](https://www.anthropic.com/) to generate briefs, weekly reviews, and chat replies. What the prompt carries is assembled in `api/src/beats/coach/context.py`, and it is more than the timer data:

- your sessions — project name, start time, duration, and the session note if there is one
- your projects' weekly goals — on a day job, that is the contract's weekly hours and where they come from (the percentage of a part-time term, `full-time`, or just `contract` for custom hours), in one line (`Acme: 33.6h/week (contract, 80%)`). Absences, the holiday region, company holidays, balance adjustments and the overtime balance are not sent.
- 30-day aggregates, plus anything stored in coach memory
- **calendar event titles and times for the day**, if Google Calendar is connected
- last night's biometrics — sleep, HRV, resting heart rate, readiness — if a health source is connected
- flow signals from the daemon, including the repository and language you spent most time in

Anthropic processes that data under their terms; Beats does not send it anywhere else.

If you do not want any data leaving the Beats database, do not use the coach.

## Export and deletion

- **Export**: anytime, via `/api/export` — your projects (contract included, archived ones too), sessions, absences and balance adjustments as a JSON backup you can import again, or your sessions as CSV. Plans, webhooks, signals, biometrics and coach history are not in it yet.
- **Deletion**: email me at <ahmed.elghareeb@proton.me> from the address on your account and I will delete every document associated with your user — projects, sessions, contracts, absences, balance adjustments, coach history, biometrics, flow signals and paired devices — and reply to confirm. Uninstalling an app or unpairing a device removes what it kept on that device but does not delete your account.

## Changes

This file is versioned in the repo. Material changes show up in `git log PRIVACY.md`.

If you have a question, open an issue or email me.
