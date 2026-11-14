# Telling customers what is happening

Shipped 2026-11-14. The public status page at `lifepete.com/status`, and the
banner in the app, written from the back office. Planned 2026-11-08 as stage
7 of the control plane's redesign, and kept in a file of its own because it is
not an operator feature: the operator is only who writes to it.

## What it has to survive

**The page must work when the API is down**, which is the only time it
matters. So it reads nothing from the API or from Mongo, and it is not served
by Cloud Run. Everything else here follows from that.

## The shape

- **One public JSON file**, `status.json`, in a small Cloud Storage bucket of
  its own (`terraform/status.tf`: `<project>-status`, uniform access, public
  read for objects, GET-only CORS for any origin, and the operator's
  `roles/storage.objectUser` on this bucket alone, never at the project
  level; gated on `operator_enabled`, since without an operator nobody writes
  it). The file holds the current state, a short message, what is affected,
  and the last twenty posts. **Written whole each time.** CORS names no
  origin (decided 2026-11-14): the file is public to anyone already and the
  browser sends no credential for it, so a list hides nothing and only
  decides which copies of the SPA can show the banner — and the same build is
  served on Firebase's own hosts for the site as well as at lifepete.com.
- **The page is `lifepete.com/status`**, on Firebase Hosting with the SPA
  (`ui/client/pages/status/Status.tsx`), so no new DNS and no new
  certificate. A public route outside `ProtectedRoute` and `Layout`, and it
  imports nothing that needs a session. The URL comes from `VITE_STATUS_URL`
  (set in `.github/workflows/ui.yml`); unset, which is the self-hosted
  default, there is no route and no banner. Its failure state says the status
  could not be loaded, and never "all good".
- **The same file drives a banner in the SPA**
  (`ui/client/shared/ui/status-banner.tsx`), shown only when the state is not
  operational: in the shell, and floating at the foot of the public pages —
  the home page, a report link, the sign-in callback and the not-found page —
  clear of their own headers, since someone who cannot sign in during an
  outage is on the home page. It polls about once a minute and, if the fetch
  fails, shows nothing; it never holds up or breaks the app.
- **Written by two commands through the runner**, `status.publish` and
  `status.clear` (`api/src/beats/operator/status_page.py`), inline, in the
  audit like any other, behind the review page, which shows exactly what will
  go public before it does. The states are a fixed list (`operational`,
  `degraded`, `outage`, `maintenance`) and the affected parts are a fixed list
  (web app, api, sign-in, coach, integrations, phone apps); the message is at
  most 280 characters. They write through the `StatusStore` port — GCS over
  `httpx` with a metadata-server token, a memory store in tests — with
  `Cache-Control: public, max-age=30`, because Cloud Storage's default for a
  public object is an hour of caching and "we're back" must not arrive an
  hour late. Clearing is a post of its own, so the page says when it ended.
- **A post goes on top of the file its review showed.** The preview hands
  back the file's generation with what it read (`generation` in the review's
  "now"), the act sends that generation as an argument, and the write is
  conditional on it (`ifGenerationMatch`): a post someone made between the
  review and the act is never replaced unseen (409 `STATUS_CONFLICT`: review
  again, publish again). An act that names no generation is refused (409
  `STATUS_NOT_REVIEWED`); the review page sends it, and so must anything
  else that drives the runner.
- **A file that cannot be read is an error, not an empty history.** If
  `status.json` is there but is not a status file, both commands refuse
  (409 `STATUS_UNREADABLE`) rather than write a one-post file over twenty
  posts; it is put right by hand in the bucket — fixed, or deleted to start
  again — and Today says so meanwhile. A bucket that does not answer is said
  too: the read answers `problem: "unreachable"`, an act answers 503
  `STATUS_UNREACHABLE` in the error envelope, and Today offers no publish
  while it lasts.
- **A person publishes every post.** The back office drafts nothing
  automatically from an alert. Whether an outage is one customers should hear
  about is a judgment. Today shows what customers currently see and the way to
  say more.
- **Little to configure.** The bucket is named by `OPERATOR_STATUS_BUCKET`,
  set by Terraform; unset, the commands answer 409 `STATUS_UNAVAILABLE` and
  Today says there is no public page to write to. `VITE_STATUS_URL` is the
  one value a deployment sets by hand, in its web build, because the web
  app's build does not know the project.

## What must not happen

- **Nothing about a person in a post**: no account, organisation, id, count of
  those affected or internal hostname. The file is public and its history is
  kept. The review shows the words whole; nothing checks them but the operator.
- **No email, and no push.** PRIVACY.md says LifePete sends no email, and
  changing that is [roadmaps/account-emails.md](../roadmaps/account-emails.md)'s
  argument to have. Push is [roadmaps/server-push.md](../roadmaps/server-push.md)
  (#298), which is not built.
- **No hosted third-party status page.** It would be a new subprocessor in
  PRIVACY.md, and its subscriber lists a new place holding customers' addresses.
- **It stands alone.** It depends on no incident record (docs/backoffice.md
  § *Decided against*). If those are built later they can prefill a post.

Every browser now asks Google for this file, which shows Google the visitor's
address; PRIVACY.md § *The status page* says so, as it does for Google Fonts.
