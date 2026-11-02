# Data Processing Agreement — draft skeleton

> **Draft** (#352) — a working skeleton in plain language, **not legal
> advice and not ready to sign**. It exists so counsel starts from the
> product's real architecture instead of a generic template that promises
> things the product deliberately does not do (or misses what it does
> better). Brackets are of three kinds. [Organisation] is the customer's
> name, filled per customer. [operator entity] and the breach [hours] are
> the operator's to fill, not the customer's; today the operator is one
> person, the one PRIVACY.md names. The rest are notes for whoever writes
> the final text with counsel.

**Parties.** [Organisation] (the **controller** of its working-time
records) and [operator entity] (the **processor**), under art. 28 GDPR.

## 1. What is processed, and for whom

The controller's instruction is the product's contract itself
(docs/organisations.md): on the organisation's own projects, each member's
entries (start, end, duration, note, and who entered it when a decider
did), absences (date, type, half day), contract terms, balances and the
adjustments behind them, absence requests (date, type, half day, the
member's note to the decider, the decision and its comment), and
timesheets with their frozen figures and approval history; the teams; the
audit log; the membership roster (name, email, role, when each joined and
left); and invitations and join requests (the address an invitation names,
a requester's name and email).

**Deliberately outside this DPA's scope** because the processor never
makes it available to the controller: everything else in a member's
account. The member's personal projects, flow scores, biometrics, calendar,
coach history and tags are processed for the **member as their own
controller's instruction**, not for the organisation, and no setting of the
organisation changes that. The DPA should say this plainly: it is the
product's main privacy property, and it narrows the controller's risk.

- Data subjects: the organisation's members, current and former, erased
  ones included (section 3) — the employees and contractors it assigns to
  projects, and those who run it (owners, admins, managers and viewers,
  who may hold no assignment), whose acts the audit log and the approvals
  record; and people who are not members: whoever an invitation names, and
  whoever asked to join.
- Duration: the term of the agreement under which the organisation uses
  LifePete, plus the retention below.
- Nature and purpose: recording working time as CJEU C-55/18 and national
  law require, including time a decider enters for a member; timesheet
  approval; absence management; managing a member's contract and balance
  where the organisation holds them; running the membership (invitations,
  join requests, roles, teams).

## 2. Processor obligations (art. 28(3))

- Process only on documented instruction — here, the product's documented
  reads and writes; anything beyond them is a new instruction in writing.
- Confidentiality: [who has access at the operator; today a single
  operator, which PRIVACY.md states outright — keep the DPA as honest].
- Security (art. 32): [reference a TOMs annex: passkey (WebAuthn) sign-in —
  lifepete.com configures no single sign-on provider, and SSO per
  organisation is not built (#342); per-user scoping at the query layer;
  the organisation wall as a separate code path; encrypted transit;
  provider-managed encryption at rest; the organisation's audit log of the
  acts inside it (docs/organisations.md, decision 12), which does not
  record the operator's own reads of the database; open source as
  auditability].
- Sub-processors (art. 28(2), general authorisation + notice):
  - Google Cloud (API hosting: Cloud Run in europe-west1, Belgium; its
    request logs in Cloud Logging, whose buckets are `global`)
  - MongoDB Atlas on Google Cloud (the database, europe-west1 —
    api/README.md § Infrastructure)
  - Google Firebase (web app hosting)
  - Anthropic (the coach) — only at the member's own use, and never
    another member's data, but **not only the member's personal data**: a
    brief or a chat carries the member's own sessions, those on the
    organisation's projects among them with their notes, and the week and
    balance of a day-job contract held on one of its projects
    (`coach/context.py`). Those rows are also the controller's record.
    [Counsel: whether this makes Anthropic a sub-processor of the
    controller's data, or the member's own use of their own data; the
    product alternative is to leave stamped rows out of what the coach
    reads.]
- Assistance with data-subject rights: a member reads the controller's
  record of them a month at a time on the "What [Organisation] can see"
  page (the record's own read narrowed to them, with a CSV), and reads
  their own timesheets and absence requests. The page and the archive of
  their own rows that are the record, with its CSV, stay open to them
  after leaving. Two things they cannot read themselves: the audit log,
  which names them but which only the controller's owners and admins read,
  and anything once their account is erased, though the controller keeps
  their rows under a tombstone (section 3). Those requests go to the
  controller, which answers from its own reads; any further assistance
  from the processor is [per counsel]. A member corrects their own
  entries, before and after leaving, until a month is approved; inside an
  approved month the controller reopens it first (docs/organisations.md,
  decisions 19 and 23).
- Breach notice to the controller without undue delay: [hours] from
  awareness.
- Audits: for an open-source product, the code and this documentation are
  the standing audit; on-site audit terms [per counsel].

## 3. Retention, return and deletion

- Working-time records are kept for the organisation's retention period,
  counted from each record's date. The period is the organisation's own
  setting, never below the statutory floor of its country — e.g. four
  years in Spain (art. 34.9 ET), two in Germany (§16(2) ArbZG) — and four
  years by default (docs/organisations.md, decision 30). At expiry a
  living member's rows lose the organisation's stamp and stay the
  member's own; only a deleted account's tombstoned rows are deleted.
  Nothing applies expiry on a schedule: the operator runs the purge by
  hand, and during the beta nobody does, so a record can outlive its
  period.
- A member's account deletion does not delete the controller's record:
  their entries and absences, the contract and adjustments behind a
  balance it read, their timesheets with their history and the audit
  entries naming them survive under a tombstone id that no account has,
  with the roster's name, email and role. Nothing else of the member's
  account does: the notes on those absences and adjustments, their absence
  and join requests and their place in teams go with it. What survives
  goes row by row as each passes the retention period above, when the
  operator runs the retention purge — the name, email and contract with
  the last row — or all at once when the organisation is deleted (below)
  (PRIVACY.md § Export and deletion; docs/organisations.md, decisions 3,
  29 and 30).
- At the end of the agreement (art. 28(3)(g)): export, then deletion,
  and deletion does not wait for the retention period above. Closing an
  organisation runs on notice of at least 30 days (60 by default), during
  which tracking carries on and the controller takes its final
  `record.csv` and `compliance.csv`: that export is the copy which
  survives, and the processor keeps nothing for the rest of the statutory
  period. From the closing day, deletion hands each member a personal
  copy of every project they hold rows or a contract on, their rows moved
  onto it and no longer anybody's record (the member's own data from then
  on, outside this agreement, as in section 1), then erases everything
  that was the organisation's, its record and a deleted account's
  tombstoned rows included (docs/organisations.md, decision 29).

## 4. Still to settle with counsel

- Governing law and venue; liability caps; the art. 28(3)(h) audit clause.
- International transfers. The API and the database are in the EEA. Not
  bound to it: Anthropic (US); Cloud Logging's `global` buckets and
  Firebase Hosting, which may store and process data anywhere Google has
  facilities; and Google Fonts, from which every page of the web app takes
  its typefaces (PRIVACY.md § The website). For those, SCCs or an adequacy
  basis. Anthropic needs its own assessment: the member's sessions on the
  organisation's projects reach it (section 2), so absence of transfer
  cannot be claimed while the coach reads them.
- Whether the operator's single-operator honesty (PRIVACY.md) needs a
  matching confidentiality undertaking in here.
