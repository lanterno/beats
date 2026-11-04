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
| [backoffice.md](backoffice.md) | The operator's control plane (#424): what needs attention, accounts, organisations, abuse and limits, capacity and cost, and compliance — operational metadata, never user content |
| [secret-manager.md](secret-manager.md) | The API's four secrets out of its Cloud Run spec, its Terraform state and its tfvars, and onto a service account of its own — what the control plane's deploy-state reads wait on |
| [billing.md](billing.md) | Invoices — the one unbuilt idea left from billing, and the two decisions already made that shape it |
| [legal/](legal/) | Three drafts for #352, awaiting counsel: a processing agreement, a works-council sheet, a DPIA template |

Five of these were split out of `organisations.md` on 2026-10-31. The test
each had to fail to stay: **is it an organisations feature?** A control
plane, push, an account's addresses, taking money and an identity protocol
are none of them, and filing them under the epic was shaping each around one
view of one feature. Three of the epic's own items wait on one of them
(#341 on the addresses, #345 on the money, #351 on push), and its file
keeps, for each of those three, the paragraph saying what stays the epic's
when the blocker clears.

## What belongs here

A plan behind an epic. A design seed nobody has started. A mockup of
something still being argued. A draft awaiting review. **And the open work
itself**: what a plan still owes is written in its own file, under a *Work*
section, step by step. A bug or a follow-up that belongs to no plan gets a
file of its own here. Issues already filed are cited by number; new work is
not filed as one (decided 2026-11-04).

Two things that look like roadmaps and are not:

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

What points at it changes in the same edit. If the whole file moved, its
row in the table above goes and [docs/README.md](../docs/README.md) gains
one. Every link into it is rewritten, not only repointed, because a sentence
that sends a reader here says the thing is not built: `CLAUDE.md` names
several roadmaps by path, `docs/` and the other roadmaps link here, and
issue bodies link to their headings. `git grep -n '<file>'` from the root
finds the first three, and
`gh issue list --state all --search '"roadmaps/<file>" in:body'` the
issues. Nothing else will — when `organisations.md` was split and its
headings renamed on 2026-10-31, the links to them from #340, #342, #343
and #351 broke without a sound.
