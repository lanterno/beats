# Data Processing Agreement — draft skeleton

> **Draft** (#352) — a working skeleton in plain language, **not legal
> advice and not ready to sign**. It exists so counsel starts from the
> product's real architecture instead of a generic template that promises
> things the product deliberately does not do (or misses what it does
> better). Bracketed parts are per-customer.

**Parties.** [Organisation] (the **controller** of its working-time
records) and [operator entity] (the **processor**), under art. 28 GDPR.

## 1. What is processed, and for whom

The controller's instruction is the product's contract itself
(docs/organisations.md): on the organisation's own projects, each member's
entries (start, end, duration, note), absences (date, type, half day),
contract terms and balances where managed, timesheets and their approval
history, the audit log, and the membership roster (name, email, role).

**Deliberately outside this DPA's scope** because the processor never
makes it available to the controller: everything else in a member's
account. The member's personal projects, flow scores, biometrics, calendar,
coach history and tags are processed for the **member as their own
controller's instruction**, not for the organisation, and no setting of the
organisation changes that. The DPA should say this plainly: it is the
product's main privacy property, and it narrows the controller's risk.

- Data subjects: the organisation's members (employees and contractors it
  assigns to projects).
- Duration: the membership agreement's term, plus the retention below.
- Nature and purpose: recording working time as CJEU C-55/18 and national
  law require; timesheet approval; absence management.

## 2. Processor obligations (art. 28(3))

- Process only on documented instruction — here, the product's documented
  reads and writes; anything beyond them is a new instruction in writing.
- Confidentiality: [who has access at the operator; today a single
  operator, which PRIVACY.md states outright — keep the DPA as honest].
- Security (art. 32): [reference a TOMs annex: passkey/SSO auth, per-user
  scoping at the query layer, the organisation wall as a separate code
  path, encrypted transit, provider-managed encryption at rest, the audit
  log; open source as auditability].
- Sub-processors (art. 28(2), general authorisation + notice):
  - Google Cloud (API hosting, EU region [region])
  - MongoDB Atlas / GCP (database, [region])
  - Google Firebase (web app hosting)
  - Anthropic (the coach) — **only ever for a member's own data at the
    member's own use; no organisation record is sent** (PRIVACY.md lists
    exactly what the coach carries). Named so the exclusion is on paper.
- Assistance with data-subject rights: the member's own export covers
  access; the "What [organisation] can see" page gives subjects a live
  view of everything processed for the controller.
- Breach notice to the controller without undue delay: [hours] from
  awareness.
- Audits: for an open-source product, the code and this documentation are
  the standing audit; on-site audit terms [per counsel].

## 3. Retention, return and deletion

- Working-time records are kept for the statutory period of the
  controller's jurisdiction — e.g. four years in Spain (art. 34.9 ET), two
  in Germany (§16(2) ArbZG) — counted from each record's date
  [docs/pricing.md and docs/organisations.md, retention decision: a
  per-organisation setting with a statutory floor; default four years].
- A member's account deletion does not delete the controller's record: the
  rows survive under a tombstone with the name the organisation knew the
  member by, and nothing else of the member's account survives
  (PRIVACY.md § Export and deletion).
- At the end of the agreement: export in CSV/JSON on request, then
  deletion when the statutory period allows. Both exist: closing an
  organisation runs on notice of at least 30 days, during which the final
  `record.csv` and `compliance.csv` are taken — that export is the copy
  which survives — and deletion then hands each member a personal copy of
  the projects they hold rows on before erasing everything that was the
  organisation's (docs/organisations.md, decision 29).

## 4. Still to settle with counsel

- Governing law and venue; liability caps; the art. 28(3)(h) audit clause.
- International transfers if any region above is outside the EEA (SCCs or
  an adequacy basis; Anthropic needs its own assessment even though no
  controller data reaches it — absence of transfer is the cleaner claim).
- Whether the operator's single-operator honesty (PRIVACY.md) needs a
  matching confidentiality undertaking in here.
