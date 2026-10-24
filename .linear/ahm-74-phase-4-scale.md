---
linear: unfiled
title: "Organisations: scale — teams, the money permission, SSO, SCIM, audit, per-seat billing (phase 4)"
team: AHM
project: lifepete
milestone: none
labels: [api, ui, Feature]
state: Backlog
priority: 4
parent: AHM-74
---

AHM-74's fourth phase: sections 1, 5 and 7 of the epic, everything that only
matters once organisations have more than a handful of people in them. Depends
on phases 2 and 3. Expect this to split into several issues when it starts —
it is a bucket, not a unit of work.

## Scope

- Teams inside an organisation, giving managers a scope.
- Manager, Viewer / Accountant roles.
- **Seeing money as its own permission**, independent of role.
- Verified email domains: join automatically, or ask to join.
- Single sign-on per organisation, optionally required to enter it.
- SCIM provisioning.
- Audit log: membership, roles, contract changes, approvals, reopened periods,
  admin edits.
- Retention settings per organisation.
- Per-seat billing paid by the organisation, separate from the person's own
  plan, which joining or leaving never changes.
- Reports: team overview, per project and per client, CSV / PDF / full export.

## What already exists to build on

- **OpenID Connect sign-in is built and tested**: discovery, code exchange
  with PKCE and a nonce, every ID-token check, identities keyed on issuer +
  subject, `allow_signup`, and a scripted provider with real RS256 keys to
  test against (`src/beats/auth/oidc.py`, `sso_accounts.py`,
  `api/routers/sso.py`, `test_sso.py`, `fake_idp.py`). Per-organisation SSO is
  a scoping and policy layer over this, not a new protocol.
- **The money wall is already a collection boundary.** Clients, project
  billing, billable overrides and billing budgets live in their own
  collections under `/api/clients` and `/api/billing`, outside every device
  prefix, with no coach port (`docs/billing.md` decisions 2 and 14). The money
  permission therefore has a real seam to attach to rather than needing one
  carved out — `docs/billing.md` already notes that `NOT_FREELANCE` can loosen
  to "you are a contractor on it" without moving data.

## Worth deciding before building, not during

- **The money permission is the one that must not be bolted on.** Every other
  item here is additive; this one is a cross-cutting read rule, and the
  cheapest version — checking a flag in each billing route — is the version
  that leaks the first time someone adds a route and forgets. The collection
  boundary above is the thing to lean on.
- **Per-seat billing is the first time money flows *to us*.** Nothing in the
  codebase handles payment today. That is a dependency (a payment provider,
  tax handling, invoices, dunning) well outside the shape of this epic, and
  probably its own project rather than a bullet in phase 4.
- **The audit log is cheap to add late and expensive to backfill.** If phases
  2 and 3 ship without it, every membership change, contract edit and approval
  before it exists is unrecorded — and those are exactly the events a works
  council would ask about. Consider writing the log in phase 2 even if nothing
  reads it until phase 4.

## Blocked on

Phases 2 and 3, and AHM-74's pricing decision (seat price, free tier for small
teams, whether contractors count as seats), which is commercial rather than
technical but gates the per-seat billing work entirely.
