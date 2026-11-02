# Server push

Telling someone something while the app is shut. Issue **#298** — APNs on
Apple, FCM on Android — and the thing several features are waiting behind.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31,
where it sat as the blocker on #351 (telling a member a month is still to
submit, or a decider that a request waits). Push is not an organisations
feature: it is a platform capability the companion, the phone apps and the
coach all want, and shaping it around timesheets would be the tail wagging
the dog. The brief, review, drift and timer-suggestion notifications are
#298's own case, and the Live Activity bridge (#313) has no other way to
move an iPhone's activity when the timer starts on the Mac.

**Decided 2026-10-31 by the owner**: push is the channel — not email — and
**the person controls what they get**.

---

## What is there now, and why it is not enough

Every notification LifePete sends is **raised on the device that shows
it**. The companion raises its own from a poll of the API and from the
Mac's idle time (`companion/lib/state/idle_watcher.dart`); the daemon,
already a background process on the desktop, raises drift and timer
suggestions (`daemon/internal/notify`); the web app raises a long-timer
reminder from an open tab (`ui/client/shared/lib/useTimerNotification.ts`).
No server reaches a device. The companion's poller,
`companion/lib/services/notification_poller.dart`, says so on itself:

> **Limitations of the free-tier path**: this is *not* true server-pushed
> delivery. If the user closes the app and the coach generates a brief at
> 7 AM, they won't see the notification until they reopen.

Every five minutes it polls today's brief from the coach, and recent drift
and pending auto-timer suggestions from `/api/signals` (with the last ten
minutes' flow windows, for the hold below), fires through
`flutter_local_notifications`, and dedupes per kind and id in
SharedPreferences (`notification_dedupe.dart`) so a brief never fires twice.
PRIVACY.md states the consequence as a feature: *"No push service is
involved."*

What already works and should be kept: **the preference model**. `Prefs`
(`companion/lib/state/prefs.dart`) has a switch per kind — `briefOn`,
`suggestOn`, `driftOn` — and `holdingInFlow`, which holds the brief and
drift nudges back while the person is in flow. A timer suggestion is not
held: flow does not make time going untracked less urgent. `askingOnIdle`,
the time-away question, is a fourth switch, but it reads the Mac's own idle
time, so there is nothing in it for a server to send. That is the shape the
owner's "the person controls what they get" asks for, and it exists; push
should extend it, not replace it.

Nor does push replace the poller. The Linux and Windows builds can reach
neither APNs nor FCM, an Android phone without Google Play cannot get FCM,
and a self-hosted server holds neither credential, since both belong to
whoever publishes the app; on all of these the poller carries on, and the
time-away question and the daemon's own notifications stay on the device
everywhere. The poller's dedupe is per install and the server cannot see
it, so a brief pushed at 07:00 fires again on the first tick after the app
opens. On an install holding a push token, either the poller stops asking
for the kinds push carries, or both send one identifier the OS merges:
`apns-collapse-id` on Apple, the notification `tag` on Android. FCM's
`collapse_key` is not that: it only drops messages Google has not yet
delivered.

## The constraint that decides the architecture

**Cloud Run, request-based billing, `min_instances = 0`**: CPU only while a
request is handled (`terraform/variables.tf`; `terraform/cloudrun.tf` sets
no billing annotation, so Cloud Run's default holds). Whether to keep one
instance warm is open in #402, and the answer changes nothing here. A warm
instance under request-based billing still has no CPU between requests;
instance-based billing would give it some, at the price of paying for it
all day, but Cloud Run may still shut a warm instance down at any time, and
a scheduler inside the API would fire once per instance as soon as there
are two (`max_instances = 2`). Two consequences, and they rule out the
obvious design:

1. There is **no always-on process** to wake at 07:00 and send anything. A
   scheduler has to come from outside: Cloud Scheduler or Cloud Tasks
   hitting an authenticated endpoint, or Pub/Sub. That is an infrastructure
   decision with a cost, and it is the first thing to settle.
2. **A detached task after the response is not reliable.** The instance may
   be throttled or gone the moment the response is written.

The one place that already fires-and-forgets is the webhook dispatcher
(`api/src/beats/api/routers/webhooks.py`), and it carries the scar in a
comment: `asyncio.create_task` keeps only a weak reference, so Python's GC
reaped in-flight dispatches until a strong-ref set was added. **Push must
not copy that pattern at a larger scale.** A send that matters is a queued
job, not a task the request leaves behind.

## What it needs

- **A push token per install** — an APNs/FCM registration token, which
  rotates, and is not the same thing as a `DeviceRegistration`
  (`domain/models.py`: a paired daemon, wall clock or companion app holding
  a device JWT).
  Whether to extend that model or give push tokens their own collection is
  a decision; they have different lifetimes and different revocation. The
  Live Activity bridge (#313) adds a third lifetime: ActivityKit gives each
  Live Activity its own APNs token, which can change while the activity
  runs and is no use once it ends, so the model must not assume one token
  per device.
- **A sender**, with retries and a dead-token path: APNs and FCM both answer
  "this token is gone", and a token that is gone must be deleted rather than
  retried for ever. A phone left in a drawer is answered late or not at all,
  so the app sends its token every time it starts, the server keeps when it
  last did, and a token unseen for longer than a window is pruned. FCM's
  default window is a month; it must be longer than the gap between the
  slowest notifications, or a member who acts on a monthly reminder (#351)
  on the web, without opening the app, loses the next one. A queued job can
  run twice, and a retry can follow a send that went through, so the sender
  keeps a record of what it has sent to whom, by kind and id: the dedupe
  `notification_dedupe.dart` does on the device today, moved to where the
  sending is. Billing keeps no such record for its budget alerts, which is
  part of why pushing them was left out
  ([docs/billing.md](../docs/billing.md) § Left out of 1b).
- **Recipients worked out when the job runs**, not when it was queued. A
  job can wait and be retried; by then the person may have left the
  organisation, lost the role or the team that made them a recipient, or
  turned that kind off. The job says what happened; the sender asks, at
  send time, who should hear of it and whether they still want to.
- **Preferences on the server**, because the server decides what to send.
  Today they are on the device, in SharedPreferences. The per-kind shape
  carries over; where it lives does not.
- **Holding in flow, on the server.** On the device the hold is free: a
  held brief or drift is simply not marked sent, so the first tick after
  flow drops fires it (`notification_poller.dart`). The flow windows are
  already on the server (the daemon posts them to
  `/api/signals/flow-windows`), so the check moves; the waiting does not.
  With no process between requests, a held send is a job put back to be
  looked at again, which is the scheduler's work, not the request's.
  Without the daemon there are no flow windows, and nothing is held.
- **The person's timezone, stored.** The API keeps none: every read takes
  `tz` per request and falls back to UTC (`get_timezone`,
  `api/src/beats/api/dependencies.py`), and `User` has no timezone field.
  A brief sent at 07:00 needs one on the server, and so does the brief
  itself, which `generate_brief` (`api/src/beats/coach/brief.py`) keys on
  the day in that timezone: without one, a scheduled brief is UTC's day,
  and the app asking for today's in its own timezone does not find it. The
  companion already sends `tz` with the brief; keeping it is a new stored
  field, which [DATA.md](../DATA.md) and PRIVACY.md then list. Whether a
  month has ended, for #351, is judged in the organisation's own
  `timezone`, which is stored
  ([docs/organisations.md](../docs/organisations.md) § Data model).
- **Per-platform credentials**: the APNs signing key (a `.p8`, with its key
  and team ids) is a secret, and there is no pattern to follow yet. A
  signing key, not a certificate, because Live Activity pushes (#313) are
  accepted only over a token-based connection. Secret Manager holds one
  thing, `terraform.tfvars`, as a blob Cloud Build fetches
  (`terraform/cloudbuild.tf`); the API's own secrets reach Cloud Run as
  plain environment values (`JWT_SECRET` in `terraform/cloudrun.tf`), and
  so sit in Terraform state too. Whether the `.p8` follows them or is the
  first secret mounted from Secret Manager is a decision. FCM needs no key
  if the Android app is registered in the Firebase project that already
  hosts the SPA: that is `beats-476914` (`ui/.firebaserc`), the API's own
  project, so the API calls FCM as the service's identity through
  Application Default Credentials. That identity is the Compute Engine
  default service account, which holds Editor on the project, so a send
  would work today with no grant at all. That is the accident to avoid:
  the right to message every phone belongs to an account granted it in
  `terraform/`, not to one that holds Editor.

## What must not happen

- **A push payload goes through Apple's and Google's servers.** So it says
  *that* there is something, never *what*: "your brief is ready", not the
  brief; "a request is waiting", not who asked for what. Nothing from a
  session note, an absence, or a client. The app fetches the content behind
  the session when it opens.
- **An employer must not be able to turn on a notification its members
  cannot turn off.** The preference is the person's. An organisation may
  cause a notification to exist; it may never own the switch.
- **Change PRIVACY.md before the release that adds it**, not after. The page
  currently says the phone apps involve no push service, and the only
  outside services it names for them are Google's ML Kit (the scanner's
  diagnostics) and Google Fonts. Push adds Apple or Google seeing a token
  and delivery metadata; the FCM SDK also collects the app's version and
  brings in Firebase installations, which mints an ID per installation. The
  same release changes three more places: the page's line that the phone
  stores "which notifications you want", since the preferences move to the
  server; DATA.md, which gains the token and the preferences (its § Devices
  names only the wall clock); and the Play Console's Data safety answers in
  `companion/store/README.md`. The page has no section for the Mac app, and
  APNs reaches the Mac too, so § The phone apps is not the only place push
  is written. PRIVACY.md has already made this promise in this exact shape
  for HealthKit — *"it will be opt-in, and this page will say so before the
  release that adds it"* — and the same words should hold here.
- **The API still sends no email** (decision 11 in
  [docs/organisations.md](../docs/organisations.md)). Push is not email,
  and this is not the thing that revisits that rule; verification for
  [account-emails.md](account-emails.md) is.
- **Off must be a real default for anyone who wants it**, including off
  entirely. A product whose pitch is that it is not surveillance does not
  get to be the app that cannot stop buzzing.
