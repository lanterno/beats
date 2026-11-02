# DPIA template — LifePete working-time records

> **Draft** (#352), not reviewed by counsel; that review is the whole
> blocker, and the template must not reach a customer before it. A data
> protection impact assessment is the **customer organisation's** document
> (art. 35 GDPR); this template prefills the parts that describe LifePete
> so their DPO starts from facts. Bracketed parts are the organisation's
> own, except those marked "counsel", which are questions for counsel
> before this goes out. Whether a DPIA is required at all is their call —
> time recording alone usually is not, but co-determination under §87(1)
> Nr. 6 BetrVG and some DPAs' blacklists (systematic monitoring) make
> having one ready the cheaper path. The AEPD's employment guidance
> expects a legal-obligation basis and minimisation; both are prefilled
> below.

## 1. Description of the processing

- **Purpose**: recording daily working time as required by [member state
  implementation of the Working Time Directive; CJEU C-55/18], timesheet
  approval, absence management.
- **Legal basis**: art. 6(1)(c) GDPR — the employer's legal obligation to
  record working time. No consent is sought and none is needed for the
  record itself [AEPD, *La protección de datos en las relaciones
  laborales*].
- **History a member chooses to share**: a member who connects a project
  they already tracked picks the day from which its hours are the
  organisation's. Nothing bounds that day but today, so it may lie before
  they joined (docs/organisations.md, rule 4 and decision 8). Entries and
  absences before it stay theirs alone; a contract on the project is
  shared with it, terms included (decision 32). This history reaches the
  organisation by the member's choice. [counsel: the basis for history
  from before the membership.]
- **Categories of data**: per member, on the organisation's projects
  only — entry start/end/duration/note, and who entered an entry when a
  decider did; absence date, type (`vacation`, `sick` or `other`), half
  day; the contract (its dated terms, holiday region, company holidays
  with their names, the region's public holidays it does not give,
  opening balance, end date and vacation entitlement), its balance and
  the adjustments behind it; absence requests (date, type, half day, the
  member's note to the decider, the decision and its comment);
  timesheets with their status, comments and history (each submit,
  decision, reopen with its reason, and terms change), and an approved
  month's frozen figures; per-day breaks, totals and rest and
  maximum-hours warnings, derived on each read and never stored. Across
  the organisation: teams; the audit log of acts inside it; the roster
  (name, email, role, when each joined and left, and how each left);
  invitations (the address one names) and join requests (the requester's
  name and email). **Sick days:** because an absence's type can be
  `sick`, the organisation learns which days a member was off sick. No
  diagnosis is held, and the record never shows an absence's note; on a
  contract the organisation manages, though, a day off is asked for with
  a note to the decider, who reads it (docs/organisations.md, decision
  22). [counsel: whether a `sick` absence is data concerning health
  under art. 9 GDPR (cf. CJEU C-101/01 *Lindqvist*), and if so the art.
  9(2) exception relied on under national law.] No location, no device
  telemetry, no app or website activity, no health readings (the product
  holds sleep, heart-rate variability, resting heart rate, readiness,
  steps and workouts from a connected health source for the person's own
  use; it is structurally unavailable to the organisation — document
  this as a mitigating design fact, not a policy).
- **Data subjects**: [employees / contractors assigned to projects]; those
  who run the organisation (owners, admins, managers, viewers), who may
  hold no assignment; former members, those who deleted their account
  included, whose rows are kept under a tombstone (docs/organisations.md,
  decision 3); and people who are not members: whoever an invitation
  names, and whoever asked to join.
- **Recipients**: inside the organisation, by role [who holds each]:
  owners and admins read the whole record and its CSVs, every contract,
  timesheet and absence request (the member's note to the decider
  included), the teams, open invitations, join requests and the audit
  log; managers read the record and its CSVs, the contracts, timesheets
  and absence requests of their teams' members, and the teams; viewers
  read the whole record and its CSVs, the teams and every timesheet.
  **Every member, whatever their role, sees every active member's name,
  email address, role and join date.** Outside it, the processor and its
  sub-processors (see the DPA). Separately, a member who uses the coach
  sends Anthropic, at their own request, their own sessions — those on
  the organisation's projects with the rest: project name, start,
  duration and note — and on a day job the week's figures against its
  contract (PRIVACY.md, The coach). Nothing only the organisation holds
  is sent: not its reads of other members, its roster or its audit log
  (docs/organisations.md, decision 15). [counsel: whether that is the
  organisation's processing at all, and the transfer basis for
  Anthropic.] The web app loads its two typefaces from Google Fonts, so
  Google receives a member's IP address whenever their browser fetches
  them: the first time they open it, and again once its cached copy has
  run out; the phone and Mac apps fetch the same typefaces from Google
  the first time they open (PRIVACY.md, The website; The phone apps).
- **Retention**: the organisation's own setting, counted from each
  record's date and never below the floor of its country (section 3):
  [4 years (ES, art. 34.9 ET) / 2 years (DE, §16(2) ArbZG) / other]. Left
  unset it is four years, or the floor where that is longer, so an
  organisation in Germany that means to keep two years sets two. What is
  not a dated record stays until the organisation is deleted
  (docs/organisations.md, decision 29): the roster of current and former
  members (name, email, role, when each joined and left), invitations
  with the address they name, join requests, teams, and each member's
  assignment with the contract on it. A deleted account's membership and
  assignment go once its last row has expired (section 3), and its join
  requests when the account is erased.

## 2. Necessity and proportionality

- The recording duty is statutory; the proportionality question is
  **scope**, and the scope is fixed in code rather than configuration:
  on its own projects only, the organisation reads finished entries,
  absences, and the contract with its balance, besides what the
  membership itself produces (the roster, timesheets, absence requests,
  the audit log), and nothing else of the tracker: no running timer, no
  activity signals, no personal projects. Its one glimpse of the present:
  approving a month is refused while a timer started inside it still
  runs (docs/organisations.md, decision 23). There is no admin setting
  that widens it.
- Minimisation: the record's response (`RecordResponse`) is written field
  by field, so what crosses cannot grow by inheritance; the two models it
  embeds whole, the organisation's project and a member's all-time
  totals, carry only the organisation's own fields and sums of the
  member's stamped entries. The employer's other reads are not built that
  way: a decider reads the whole contract, and an audit event's details
  are free-form. The public and member-facing documentation lists what
  the record holds.
- Transparency: every member has "What [organisation] can see" on the
  organisation's Timesheets tab: in words, what the record holds of them
  and that the contract's terms are read as well (deciders read those on
  a route of their own), and behind *See the actual data* the
  organisation's record narrowed to them, live. [Attach a screenshot;
  cite it under arts. 12–14 measures.]
- Accuracy and integrity: approval freezes a month, and every later write
  dated inside it (an entry, an absence, a balance adjustment, time a
  decider enters) is refused until a recorded, reasoned reopen. A change
  to the contract's terms, dated inside no month, is not refused: it
  marks the approved months it moves, which stay locked on their frozen
  figures (docs/organisations.md, decision 23). Until a month is
  approved, its entries are the member's to correct, before and after
  leaving, and those edits are not in the audit log (decision 19).
  Employer-side acts are in an audit log the works council can ask
  about.

## 3. Risks, and the measures against them

| Risk | Likelihood / severity | Measures |
|---|---|---|
| Function creep: the record becomes behaviour monitoring | The classic risk of time tracking | The monitoring signals are never written where the organisation can query them; the employer read is one narrow code path; open source makes the claim checkable; AI-Act art. 5(1)(f) emotion inference is structurally impossible on employer-visible data |
| A member's personal life leaks through a note | Possible, self-inflicted | Every input whose note someone in the organisation reads says so on the input itself: the session editor ("[organisation] can read this note", following the project picked) and the request for time off ("Your manager reads this note; the organisation's record never shows it"). Any surface that brings back a note input ships with the same marker (docs/organisations.md, decision 1) |
| Access beyond need inside the organisation | [org-specific] | Roles: managers scoped to their teams; viewers read-only; money (when it exists) read by owners and admins only, a capability of their role rather than a permission of its own (#340); [the organisation's own role assignments here] |
| Record manipulation before an inspection | Low | Frozen months, reasoned reopens, and an audit log of acts inside the organisation. Not covered: a month not yet approved, which the member can change without a trace (docs/organisations.md, decision 19), and a decider approving their own timesheet or absence request (decision 33). [How promptly the organisation approves each month.] |
| Unlawful retention beyond the statutory period | [org-specific] | A retention period is refused below the floor of the organisation's country, the one holiday country in its settings (Spain 4 years, Germany 2, France and the Netherlands 1, Austria 1 [counsel: §26 AZG names no retention period; the year is the limitation period for administrative penalties], Poland 10; an unknown or unset country gets 4). Every floor, Poland's included, is counted from each record's own date [counsel: art. 94 pkt 9b Kodeks pracy counts Poland's ten years from the end of the calendar year in which the employment ended]. A period never set is four years or the floor, whichever is longer. Expiry removes the organisation's record, not the person: a living member's entries and absences lose the stamp and are theirs alone. What is deleted is what existed only for the record: a deleted account's rows under its tombstone, then its membership (name, email) and assignment (contract) once none of those rows is left; timesheets for months wholly before the cutoff, frozen figures with them; decided absence requests dated before it; and audit events older than it. The purge is an operator-run script, audited with counts and no data; nothing schedules it, so nothing auto-deletes during the beta |
| Processor compromise | Low / high | [TOMs annex of the DPA; passkey (WebAuthn) sign-in and no passwords: lifepete.com configures no single sign-on provider, and SSO per organisation is not built (#342); a paired device (the daemon, a phone or Mac app, the wall clock) holds a device token, minted from a pairing code a signed-in session creates, which reads and writes entries on the organisation's projects like any other and is refused on every organisation route (docs/organisations.md, decision 14); per-user query scoping] |
| Access by the processor's own staff | [the organisation's assessment] | One operator, who can read and write every document in the database: there is no privileged-access boundary (PRIVACY.md, Who can see your data), and the organisation's audit log does not record the operator's reads. [Confidentiality undertaking per the DPA.] |

## 4. Sign-off

[DPO opinion; the works agreement under §87(1) Nr. 6 BetrVG (or the
conciliation board's ruling, §87(2)) where applicable; prior consultation
with the supervisory authority only if residual risk stays high — not
expected given the scope above.]
