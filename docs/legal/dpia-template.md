# DPIA template — LifePete working-time records

> **Draft** (#352). A data protection impact assessment is the
> **customer organisation's** document (art. 35 GDPR); this template
> prefills the parts that describe LifePete so their DPO starts from
> facts. Bracketed parts are the organisation's own. Whether a DPIA is
> required at all is their call — time recording alone usually is not,
> but §87 BetrVG consultations and some DPAs' blacklists (systematic
> monitoring) make having one ready the cheaper path. The AEPD's
> employment guidance expects a legal-obligation basis and minimisation;
> both are prefilled below.

## 1. Description of the processing

- **Purpose**: recording daily working time as required by [member state
  implementation of the Working Time Directive; CJEU C-55/18], timesheet
  approval, absence management.
- **Legal basis**: art. 6(1)(c) GDPR — the employer's legal obligation to
  record working time. No consent is sought and none is needed for the
  record itself [AEPD, *La protección de datos en las relaciones
  laborales*].
- **Categories of data**: per member, on the organisation's projects
  only — entry start/end/duration/note; absence date, type, half day;
  contract terms and balance where managed; timesheet status and history;
  name, email, role. **No special categories.** No location, no device
  telemetry, no app or website activity, no biometrics (the product holds
  biometric data for the person's own use; it is structurally unavailable
  to the organisation — document this as a mitigating design fact, not a
  policy).
- **Data subjects**: [employees / contractors assigned to projects].
- **Recipients**: [who inside the organisation holds admin, manager,
  viewer roles]; the processor and its sub-processors (see the DPA).
- **Retention**: statutory — [4 years (ES, art. 34.9 ET) / 2 years (DE,
  §16(2) ArbZG) / other], counted from the record's date.

## 2. Necessity and proportionality

- The recording duty is statutory; the proportionality question is
  **scope**, and the scope is fixed in code rather than configuration:
  the organisation's read returns finished entries on its own projects
  and nothing else — no live status, no activity signals, no personal
  projects. There is no admin setting that widens it.
- Minimisation: the record's response schema is written field by field,
  so what crosses cannot grow by accident; the public and member-facing
  documentation lists it exhaustively.
- Transparency: every member has the "What [organisation] can see" page —
  the organisation's own read narrowed to them, live. [Attach a
  screenshot; cite it under arts. 12–14 measures.]
- Accuracy and integrity: approval freezes a month; later edits are
  refused until a recorded, reasoned reopen; employer-side acts are in an
  audit log the works council can ask about.

## 3. Risks, and the measures against them

| Risk | Likelihood / severity | Measures |
|---|---|---|
| Function creep: the record becomes behaviour monitoring | The classic risk of time tracking | The monitoring signals are never written where the organisation can query them; the employer read is one narrow code path; open source makes the claim checkable; AI-Act art. 5(1)(f) emotion inference is structurally impossible on employer-visible data |
| A member's personal life leaks through a note | Possible, self-inflicted | The one input that writes a note carries the marker "[organisation] can read this note", on the input itself |
| Access beyond need inside the organisation | [org-specific] | Roles: managers scoped to their teams; viewers read-only; money (when it exists) its own permission; [the organisation's own role assignments here] |
| Record manipulation before an inspection | Low | Frozen months, reasoned reopens, audit log |
| Unlawful retention beyond the statutory period | [org-specific] | Retention floors by jurisdiction; deletion machinery audited [#344/#347 when built; until then, deletion on instruction] |
| Processor compromise | Low / high | [TOMs annex of the DPA; passkey-only auth; per-user query scoping] |

## 4. Sign-off

[DPO opinion; works-council consultation outcome under §87(1) Nr. 6
BetrVG where applicable; prior consultation with the supervisory
authority only if residual risk stays high — not expected given the
scope above.]
