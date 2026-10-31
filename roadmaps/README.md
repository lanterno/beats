# Roadmaps

**What is not built yet.** [docs/](../docs/) is the other half — what is
built, and why.

| File | What it covers |
|------|----------------|
| [organisations.md](organisations.md) | The organisations epic (#353): what it still owes, why each piece waits, and the three constraints any of them must keep |
| [organisation_sso.md](organisation_sso.md) | SSO per organisation (#342) and SCIM (#343): a per-organisation attestation over the OIDC code that exists |
| [account-emails.md](account-emails.md) | Several verified addresses on one account — what #341 waits on, and the one place decision 11's no-email rule gets revisited |
| [server-push.md](server-push.md) | APNs and FCM (#298): the channel #351 waits on, and the Cloud Run shape that decides its architecture |
| [subscriptions.md](subscriptions.md) | Collecting the per-seat price (#345). What to charge is decided in [docs/pricing.md](../docs/pricing.md); this is the machinery |
| [backoffice.md](backoffice.md) | The operator's control plane (#424): operator routes in the one API, deployed a second time behind IAP, with a UI of its own in front — accounts, organisations, abuse and limits, capacity |
| [billing.md](billing.md) | Invoices — the one unbuilt idea left from billing, and the two decisions already made that shape it |
| [legal/](legal/) | Three drafts for #352, awaiting counsel: a processing agreement, a works-council sheet, a DPIA template |

Five of these were split out of `organisations.md` on 2026-10-31. The test
each had to fail to stay: **is it an organisations feature?** A back office,
push, an account's addresses, taking money and an identity protocol are
none of them, and filing them under the epic was shaping each around one
view of one feature. The epic's own file keeps, for each, the sentence
saying what stays its own when the blocker clears.

## What belongs here

A plan behind an epic. A design seed nobody has started. A mockup of
something still being argued. A draft awaiting review.

Three things that look like roadmaps and are not:

- **Open work.** A bug, a follow-up, a question to decide: that is a
  [GitHub issue](https://github.com/lanterno/beats/issues). Files here link
  to issues and never restate them — an issue says the work is *owed*, a file
  here says why it is *shaped* the way it is. If you are tempted to write a
  checklist, you want an issue.
- **A decision not to build something.** "Left out of 1b" in
  [docs/billing.md](../docs/billing.md) reads like a to-do list and is the
  opposite of one: it records scope deliberately cut, so it is not re-argued.
  That belongs with the thing it was cut from.
- **Anything a code comment cites.** A comment describes what the code does,
  and what it does is built — so comments point at `docs/`. There are no code
  references into this folder, and that is deliberate: it is what keeps the
  two halves from drifting.

## Writing for whoever picks this up

Assume a competent stranger — quite possibly an agent — with no memory of the
decisions. That means: say what is blocked and by what, in the first screen;
name real files and issue numbers rather than describing them; state the
mistakes already avoided, because those are what a fresh reader will make;
and say what *must not* happen, not only what should.

Do not restate what `docs/` already says. If you need a rule from there, link
to it. The four rules of the organisations epic lived in both files until
2026-10-31, the two copies had already drifted, and a rule that exists twice
is a rule nobody can trust.

## When something ships

The file moves to `docs/`; if only part of it shipped, that part is **deleted
here and written there**. Never copied — two accounts of one decision
disagree the first time one of them is edited.
