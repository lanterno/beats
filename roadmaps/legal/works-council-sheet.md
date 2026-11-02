# What LifePete records — one page for the works council

> **Draft** (#352). Facts verified 2026-10; have counsel review before it is
> handed to a customer. Every claim below is checkable against the running
> product and the open source code, which is the point of it.

LifePete is a personal time tracker that an employer can read working-time
records from — not a monitoring tool with a privacy page. The difference is
structural, and this sheet says exactly where the line is so a works council
can check it rather than trust it.

## What the employer sees, in full

On **its own projects only**: each entry's start, end, duration and note
(each input that writes a note says the employer can read it); absences as
date, type (vacation, sick or other) and whole or half day; the contract a
member holds on one of its projects — its dated terms, holiday region, the
company holidays it adds and the public holidays it does not give, opening
balance, end date and vacation entitlement — and its balance; each
timesheet's status and history, who acted at each step and any reason given,
and the figures frozen when it is approved; a request for a day off, with
the note addressed to whoever decides it; and, derived from the entries on
every read, each day's first start, last end, breaks and total on each
project, and the day's compliance warnings. Of each member: the name and
email address they joined under, their role and teams, and the day they
joined. And an audit log of who did what in the organisation, and when. That
is the entire list.

Inside the organisation, owners and admins read all of it. A manager reads
the same for the members of their teams only, and not the audit log. A
viewer reads everyone's entries, absences, balances, timesheets and
compliance figures, but no contract's terms, no request and no audit log.
Any member can read the others' names, addresses, roles and joining days.

## What the employer can never see

- Whether anyone is working **right now** — the record carries finished
  entries only, no running flag, by decision and by code. The one trace of
  the present is narrow: approving a month that has ended is refused while a
  timer started inside it is still running.
- Screenshots, what was typed, websites visited — **never built**, for
  anyone, not "off by default".
- The personal tracker's own data: flow scores, tags, insights, biometrics,
  calendar, the coach, and what the optional `beatsd` daemon samples on the
  person's own computer for their flow score — which app was in front,
  which repository was open, idle time, and a count of keyboard and mouse
  events, never which keys. It is collected for the person alone, also
  while a timer runs on the employer's project, and never crosses; no admin
  setting changes this.
- Personal projects, or that they exist.

Every employee can open **"What _[employer]_ sees"** at any time (the
Timesheets tab, *See the actual data*): it is the employer's own read of
the record (entries, absences, balance), narrowed to them — the actual
data, not a description of it.

## The four rules the code keeps

1. One person, one account, one timeline — joining never creates a work
   account, leaving loses nothing personal.
2. Every project has exactly one owner; what anyone sees follows from that.
3. Hours, not the person (the lists above).
4. Nothing is retroactive without consent — connecting an existing project
   shares its entries and absences only from a day the employee chooses.
   A contract on it crosses whole, every term back to its start and the
   opening balance included, and its running balance is withheld while an
   entry or absence from before that day would be in it.

## Why this satisfies the law — and the council

- **CJEU C-55/18 (2019)**: member states must require "an objective,
  reliable and accessible system" recording daily working time. LifePete's
  record and compliance export are exactly that shape (per member, project
  and day: first start, last end, breaks, total, with rest-period and
  maximum-hours warnings judged over the member's whole day on the
  employer's projects and derived on every read).
- **BAG 1 ABR 22/21 (2022)**: German employers must already record working
  time; the works council co-determines **how**. Germany's reform
  (electronic recording) is still a ministry draft as of October 2026; it
  keeps the two-year retention of §16(2) ArbZG and LifePete already
  satisfies its electronic, same-day shape.
- **§87(1) Nr. 6 BetrVG** applies to systems that *could* monitor
  behaviour. LifePete is designed so the capability is absent, not merely
  unused: the surveillance signals are never written where an employer can
  query them, and the read that serves employers is a separate, narrow
  code path (`/record`) that a council's technical adviser can read.
- **Approved months freeze**: once a timesheet is approved, every write
  dated inside the month (an entry, an absence, an adjustment, the
  employer's own) is refused until a recorded, reasoned reopen. A change
  to the contract's terms, which span every month, is accepted rather
  than refused: the month stays locked, its figures frozen at approval
  stay the record, and it is marked as changed since approval when the
  new terms can move it. An approved month cannot drift silently. Every
  employer-side act (contract changes, approvals, reopens, admin-entered
  time) is in an audit log.
- **Retention**: Spain requires four years (art. 34.9 ET; a missing or
  incorrect register is a serious infringement, LISOS art. 7.5, fined
  €751–7,500 under art. 40.1.b — the "€10,000 per worker" figure sometimes
  quoted comes from a bill the Congreso rejected in September 2025).
  Germany: two years (§16(2) ArbZG). How long LifePete keeps the record is
  the organisation's setting: four years by default, never less than its
  country's statutory period. In Germany that floor is two years, so a
  German employer keeps four unless it lowers the setting — a figure the
  council may want to agree. Nothing deletes on a schedule: expiry is
  applied by a script the operator runs, and during the beta nobody runs it.
  The employee's departure or account deletion does not destroy the record,
  nor extend what the employer sees. The employer can delete it by closing
  the organisation, after at least 30 days' notice every member sees: each
  member keeps their own entries, and the exports taken during the notice
  are the copy of the record that survives.

## The line not crossed

The CNIL fined Amazon France Logistique €32 M over the activity indicators
its warehouse scanners computed (SAN-2023-021). On 23 December 2025 the
Conseil d'État cut the fine to €15 M (no. 492830): it set aside the finding
that three of the indicators had no legal basis, and upheld the finding that
keeping every indicator for 31 days breached data minimisation. LifePete
writes no such indicator where an employer can read it, so an employer has
none to keep. The EU AI Act art. 5(1)(f) bans AI systems that infer
emotions in the workplace. LifePete's coach and biometrics exist **for the
person only** and are structurally unreachable by the employer — which is
why this product can be signed off where monitoring tools cannot.
