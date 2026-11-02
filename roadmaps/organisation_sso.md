# SSO per organisation, and provisioning

An organisation that requires its members to enter its slice through *its*
own identity provider, and — later, and only for the tier that asks for it —
members provisioned and deprovisioned from that provider automatically.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31:
these two are their own piece of work with their own protocol surface, not
the tail of that epic, though both are tracked as tasks of its issue, #353.
What organisations already are is [docs/organisations.md](../docs/organisations.md);
**read its four rules first** — this design is shaped by them, rule 1 above all.

Two GitHub issues, neither started. **#342** (SSO per organisation) had its
shape decided on 2026-10-28, with one question left for build time, so it
is written as a design; it is blocked by nothing and waits for a customer
that requires it. **#343** (SCIM) is blocked by #342, since SCIM keys on
the provider #342 gives an organisation and there is none before it. Its
order and its tier are decided but it has no design yet, so it is written
as the constraints any design keeps.

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
  `aud`/`azp`, `exp`, `iat`, nonce), an identity keyed on issuer + subject
  and never on an email — and `src/fake_idp.py`, a scripted provider with
  real RS256 keys to test against. Provider configuration is
  deployment-wide today (`OIDC_PROVIDERS` in `settings.py`), and
  `OrgMembership` has no attestation fields. **It is not a new protocol.**
- **An organisation's provider is untrusted input.** `OIDC_PROVIDERS` is
  written by the operator, and `_require_https` in `settings.py` trusts it
  that far: it lets `http://localhost` through for development. Here the
  issuer is typed by an organisation's admin, and anyone can create an
  organisation; `OIDCProvider` fetches it, then whatever `jwks_uri` and
  `token_endpoint` its discovery document names, from inside the API's own
  network. So the per-organisation path refuses `localhost`, requires https
  on the issuer and on every endpoint discovery names, follows no redirect,
  and refuses loopback, private and link-local addresses — checked on the
  address it connects to, not on a lookup made before it. The client secret
  is write-only: no read returns it, and the audit log's `details` say it
  changed, never to what.
- Entering that organisation's slice needs a fresh verification with *that*
  provider, stored on the membership: verified at T, expiring at T+N. It
  shows on the "What Acme can see" page and is in the audit log. **The
  stored attestation must not outlive the account**: erasure keeps the
  membership document under the tombstone and rewrites only `user_id`,
  `left_at` and `left_reason` (`api/src/beats/infrastructure/erasure.py`),
  so a field added to it survives by default. The build unsets the
  attestation there, as erasure already unsets an assignment's personal
  fields; decision 3 keeps the name and address the organisation knew the
  person by, not when they last verified with its provider.
- The person's passkey still opens their personal account and every other
  organisation — rule 1. An organisation may require a door into its own
  slice; it may never require one into the person's account.
- **An organisation's provider is never a door.** Whoever administers it
  can sign in as anyone at it, so a provider that could open the account
  would hand the organisation everything rule 3 keeps from it. It is not
  offered on the sign-in page (`GET /api/auth/sso/providers`). Its flow
  starts and finishes in one signed-in session, as a link does
  (`SSO_LINK_SESSION_MISMATCH` in `api/src/beats/api/routers/sso.py`), and
  writes the attestation on the membership and its audit entry, nothing
  else: no account created, nothing added to the account's `identities[]`,
  no session issued. `api/src/beats/auth/sso_accounts.py` is the door; its
  `sign_in` and `link` are not reused here.
- Enforce it **in one place, where the role checks already are**:
  `OrganisationService._member` in `api/src/beats/domain/organisations.py`,
  which reads the membership the attestation is stored on. Almost every
  route under `/{id}` resolves its caller through it, on both routers that
  serve `/api/organisations` (`api/src/beats/api/routers/organisations.py`
  and `employment.py` beside it). Neither router declares a dependency, so
  a gate on one router would leave the other open. Never a flag per route:
  that is the shape that leaks the first time somebody adds a route and
  forgets.
- **What the gate never closes.** Leaving (`POST /{id}/leave`), what the
  organisation sees of the person (`/visible`, `/visible.csv`), their
  archive (`/archive`, `/archive.csv`) and the organisation's own page
  (`GET /{id}`, which carries a closing notice, decision 29, and which
  `GET /` already answers for every membership) answer whatever the
  attestation says. A member the provider has offboarded can never verify
  again, and must still be able to leave and to see what the organisation
  holds of them ([the rule after the four](../docs/organisations.md#the-four-rules));
  a former member has no attestation at all; and the page that shows the
  attestation cannot sit behind it. Leaving is not entering the slice.
  Name these beside the check, so a route added later is closed until
  somebody opens it. `/visible` and `/archive` already resolve the caller
  without `_member`, so that former members can read them; `leave` and
  `get` go through it.
- **Change PRIVACY.md first, and narrowly**: an organisation that requires
  SSO sees when you last verified with its provider. The sentence that
  stops being true is in the organisation's bullet under *Who can see your
  data*, "It sees nothing else", so that is where it is said. The sentence
  in *Authentication*, "nothing downstream records which door was used", is
  the one this design rests on, and it stays: this is not "we record how
  you log in", and the wording matters. DATA.md's *Organisations* section
  gains the provider and the membership's verification in the same change.

### Open at build time

Whether a lapsed attestation blocks the organisation's routes alone, or
also starting new timers on its projects. Existing data is never blocked
either way: the entries on the person's own timeline, those on its
projects included, stay theirs to read, as does everything the gate never
closes. Ask the owner when the build starts.

---

## #343 — SCIM provisioning

Provision and deprovision members from an identity provider.

Its own protocol surface and its own credential story, keyed on the same
per-organisation provider as #342, so it comes **after** it — there is
nothing for SCIM to key on until an organisation has a provider of its own.

It belongs to a later, sales-led enterprise tier, not the seat price
([docs/pricing.md](../docs/pricing.md)).

Two constraints any design keeps:

- deprovisioning means ending a membership, which is `_end_membership` —
  the same path as leaving and removal, teams included. It must not grow a
  second way to take somebody out of an organisation.
- the last-owner guard (decisions 10 and 20) applies to a SCIM
  deprovision as it does to a removal, and a provider that deprovisions the
  last owner has to be refused in a way an administrator can see.
