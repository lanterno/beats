# Telling customers what is happening

**What is blocked:** nothing else waits on this. It is stage 7 of
[backoffice.md](backoffice.md), kept in its own file because a public status
page is not an operator feature: the operator is only who writes to it.

**What blocks it:** nothing. It needs from the owner the wording of one sentence
in PRIVACY.md.

Written 2026-11-08. Today there is no status page anywhere in the repo, and no
way to reach customers during an outage.

## What it has to survive

**The page must work when the API is down**, which is the only time it matters.
So it reads nothing from the API or from Mongo, and it is not served by Cloud
Run. Everything else here follows from that.

## The shape

- **One public JSON file** in a small Cloud Storage bucket of its own: the
  current state, a short message, what is affected, and the last twenty posts.
  Written whole each time.
- **The page is `lifepete.com/status`,** on Firebase Hosting with the SPA, so no
  new DNS and no new certificate. It is a public route outside `ProtectedRoute`,
  and it must not import anything that needs a session. The URL comes from
  `VITE_STATUS_URL`; unset, which is the self-hosted default, there is no route
  and no banner.
- **The same file drives a banner in the SPA,** shown only when the state is not
  operational. It polls about once a minute and, if the fetch fails, shows
  nothing. It must never hold up or break the app.
- **Written by two commands through the runner,** `status.publish` and
  `status.clear`, inline, in the audit like any other, behind stage 1's review
  screen if that has shipped. They write through a narrow port added to
  `CommandContext` (GCS over `httpx` with a metadata-server token, a fake in
  tests, a local file in development), using `ifGenerationMatch` so two writes
  cannot silently lose one.
- **A person publishes every post.** The back office drafts nothing automatically
  from an alert. Whether an outage is one customers should hear about is a
  judgment.

## Mistakes to avoid

- **Cloud Storage's default for a public object is an hour of caching.** Set
  `Cache-Control: public, max-age=30` on every write, or "we're back" arrives an
  hour late.
- **The bucket needs CORS** for `https://lifepete.com`, GET only. There is no
  Content-Security-Policy in `ui/firebase.json` or `ui/index.html` to widen
  today; if one has arrived by then, it needs this origin.
- **Every browser now asks Google for this file,** which shows Google the visitor's
  address. PRIVACY.md describes this for Google Fonts and must say it here too.
- **The operator's service account gets `roles/storage.objectUser` on this bucket
  alone,** never at the project level. `operator_enabled` gates the grant, and the
  bucket's public read has nothing to do with it.
- **It must stand alone.** It may not depend on the incident records in
  [backoffice.md](backoffice.md) § *Not decided*. If those are built later they
  can prefill a post.

## Work

1. **PRIVACY.md and DATA.md,** approved by the owner, in their own commit.
2. **`terraform/status.tf`:** the bucket with uniform access, public read for
   objects, CORS, and the operator's grant. Check that nothing at the project
   level enforces public access prevention. Watch the first apply: a failed one
   blocks every API deploy.
3. **The port and the two commands.** The states are a fixed list (`operational`,
   `degraded`, `outage`, `maintenance`), and the affected parts are a fixed list.
   The message has a length limit.
4. **The publish panel in the back office,** showing exactly what will go public
   before it does, and the current state on Today.
5. **The page** at `/status`, in the bright design style, with a plain sentence
   first. Its failure state says the status could not be loaded, and never
   "all good".
6. **The banner** in the SPA shell. The companion can follow it later.

**Tests:** a publish leaving the old file intact when the write fails; the
generation conflict; the commands' audit rows and a `viewer` refused; the page
rendering each state and an unreachable file; the banner staying hidden on a
failed fetch.

**Done when** with the API stopped locally, the page still loads and shows the
message that was last published.

## What must not happen

- **Nothing about a person in a post:** no account, organisation, id, count of
  those affected or internal hostname. The file is public and its history is kept.
- **No email, and no push.** PRIVACY.md says LifePete sends no email, and changing
  that is [account-emails.md](account-emails.md)'s argument to have. Push is
  [server-push.md](server-push.md) (#298), which is not built.
- **No hosted third-party status page** without the owner's decision. It would be
  a new subprocessor in PRIVACY.md, and its subscriber lists a new place holding
  customers' addresses.
- **No new repository or service.** This lives in the monorepo.
