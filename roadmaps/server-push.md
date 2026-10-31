# Server push

Telling someone something while the app is shut. Issue **#298** — APNs on
Apple, FCM on Android — and the thing several features are waiting behind.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31,
where it sat as the blocker on #351 (telling a member a month is still to
submit, or a decider that a request waits). Push is not an organisations
feature: it is a platform capability the companion, the phone apps and the
coach all want, and shaping it around timesheets would be the tail wagging
the dog.

**Decided 2026-10-31 by the owner**: push is the channel — not email — and
**the person controls what they get**.

---

## What is there now, and why it is not enough

Every notification LifePete sends is **local, from a foreground poll**.
`companion/lib/services/notification_poller.dart` says so on itself:

> **Limitations of the free-tier path**: this is *not* true server-pushed
> delivery. If the user closes the app and the coach generates a brief at
> 7 AM, they won't see the notification until they reopen.

It polls the coach endpoints on a timer, fires through
`flutter_local_notifications`, and dedupes per kind and id in
SharedPreferences (`notification_dedupe.dart`) so a brief never fires twice.
PRIVACY.md states the consequence as a feature: *"No push service is
involved."*

What already works and should be kept: **the preference model**. `Prefs`
(`companion/lib/state/prefs.dart`) has a switch per kind — `briefOn`,
`driftOn` — and `holdingInFlow`, which holds a notification back while the
person is in flow. That is the shape the owner's "the person controls what
they get" asks for, and it exists; push should extend it, not replace it.

## The constraint that decides the architecture

**Cloud Run, `min_instances = 0`, CPU not allocated outside a request**
(`terraform/variables.tf`, `terraform/cloudrun.tf`). Two consequences, and
they rule out the obvious design:

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
  (`domain/models.py`: a paired daemon or wall clock holding a device JWT).
  Whether to extend that model or give push tokens their own collection is
  a decision; they have different lifetimes and different revocation.
- **A sender**, with retries and a dead-token path: APNs and FCM both answer
  "this token is gone", and a token that is gone must be deleted rather than
  retried for ever.
- **Preferences on the server**, because the server decides what to send.
  Today they are on the device, in SharedPreferences. The per-kind shape
  carries over; where it lives does not.
- **Per-platform credentials**: an APNs key, an FCM service account. Both
  are secrets, and `terraform/` already has the pattern (Secret Manager).

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
  currently says the phone apps involve no push service and name no
  third-party services at all; adding push means Apple or Google sees a
  token and delivery metadata. PRIVACY.md has already made this promise in
  this exact shape for HealthKit — *"it will be opt-in, and this page will
  say so before the release that adds it"* — and the same words should hold
  here.
- **The API still sends no email** (decision 11). Push is not email, and
  this is not the thing that revisits that rule; verification for
  [account-emails.md](account-emails.md) is.
- **Off must be a real default for anyone who wants it**, including off
  entirely. A product whose pitch is that it is not surveillance does not
  get to be the app that cannot stop buzzing.
