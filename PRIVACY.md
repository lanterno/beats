# Privacy

This is a personal, open-source project. I (Ahmed Elghareeb, [@lanterno](https://github.com/lanterno)) am the only operator. This page describes — in plain English — what Beats does with your data.

For the catalogue of every field stored, see [DATA.md](./DATA.md).

## What Beats is

Beats is a self-tracking system. It records what you work on, for how long, and (optionally) how you felt while doing it. It is not a productivity app sold to employers, and there is no analytics product built on top of your data.

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
- **HealthKit / Health Connect** — read biometrics via the companion app

You can disconnect any integration at any time. Disconnecting revokes the token on Beats' side; revoke at the provider too if you want belt-and-braces.

## The coach

The coach feature sends prompts to the [Anthropic Claude API](https://www.anthropic.com/) to generate briefs, weekly reviews, and chat replies. Those prompts include the beats, intentions, and notes you have asked the coach to consider. Anthropic processes that data under their terms; Beats does not send it anywhere else.

If you do not want any data leaving the Beats database, do not use the coach.

## Export and deletion

- **Export**: anytime, via `/api/export` (CSV or JSON). The whole dataset, not a curated subset.
- **Deletion**: email me at <ahmed.elghareeb@proton.me> from the address on your account and I will delete every document associated with your user. I will reply to confirm.

## Changes

This file is versioned in the repo. Material changes show up in `git log PRIVACY.md`.

If you have a question, open an issue or email me.
