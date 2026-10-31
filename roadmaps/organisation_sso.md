# SSO per organisation, and provisioning

An organisation that requires its members to enter its slice through *its*
own identity provider, and — later, and only for the tier that asks for it —
members provisioned and deprovisioned from that provider automatically.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31,
when the organisations epic's own bugs were cleared: these two are their own
piece of work with their own protocol surface, not the tail of that epic.
What organisations already are is [docs/organisations.md](../docs/organisations.md);
**read its four rules first** — this design is shaped by them, rule 1 above all.

Two GitHub issues: **#342** (SSO per organisation) and **#343** (SCIM).
Both are decisions already taken rather than questions still open, which is
why they are written as a design and not as a problem.

---

## #342 — SSO per organisation, optionally required

**The shape was decided 2026-10-28.** It is built when a customer requires
it, not before — but it is designed, so this is a build task. SSO is
included in the paid seat price, not an add-on
([docs/pricing.md](../docs/pricing.md)).

### Not by stamping the door on the session

Sessions stay door-blind. The promise that nothing downstream records which
door was used is kept in the code — `POST /api/auth/sso/complete` logs
neither the provider nor the account — and PRIVACY.md says so. Reaching for
the session's door would be the obvious implementation and is the one thing
this design refuses.

### A per-organisation attestation

The way GitHub gates an organisation behind SAML:

- An organisation that requires SSO configures its own OpenID Connect
  provider. This is a **scoping layer** over `api/src/beats/auth/oidc.py`,
  which is built and tested already — discovery, the code exchange with
  PKCE and a nonce, every ID-token check (asymmetric signature, `iss`,
  `aud`/`azp`, `exp`, `iat`, nonce) — plus `auth/sso_accounts.py`
  (identities keyed on issuer + subject, `allow_signup`) and
  `src/fake_idp.py`, a scripted provider with real RS256 keys to test
  against. Provider configuration is deployment-wide today
  (`OIDC_PROVIDERS` in `settings.py`), and `OrgMembership` has no
  attestation fields. **It is not a new protocol.**
- Entering that organisation's slice needs a fresh verification with *that*
  provider, stored on the membership: verified at T, expiring at T+N. It
  shows on the "What Acme can see" page and is in the audit log.
- The person's passkey still opens their personal account and every other
  organisation — rule 1. An organisation may require a door into its own
  slice; it may never require one into the person's account.
- Enforce it as **a dependency on the organisation router, in one place**,
  the way the role checks already are. Never a flag per route: that is the
  shape that leaks the first time somebody adds a route and forgets.
- **Change PRIVACY.md first, and narrowly**: an organisation that requires
  SSO sees when you last verified with its provider. That is not "we record
  how you log in", and the wording matters — see the sentence in
  *Authentication* that this design rests on.

### Open at build time

Whether a lapsed attestation blocks the organisation's routes alone, or
also starting new timers on its projects. Existing data is never blocked
either way. Ask the owner when the build starts.

---

## #343 — SCIM provisioning

Provision and deprovision members from an identity provider.

Its own protocol surface and its own credential story, keyed on the same
per-organisation provider as #342, so it comes **after** it — there is
nothing for SCIM to key on until an organisation has a provider of its own.

It belongs to a later, sales-led enterprise tier, not the seat price
([docs/pricing.md](../docs/pricing.md)).

Two things to settle before building, neither of them now:

- deprovisioning means ending a membership, which is `_end_membership` —
  the same path as leaving and removal, teams included. It must not grow a
  second way to take somebody out of an organisation.
- the last-owner guard (decisions 10 and 20) applies to a SCIM
  deprovision as it does to a removal, and a provider that deprovisions the
  last owner has to be refused in a way an administrator can see.
