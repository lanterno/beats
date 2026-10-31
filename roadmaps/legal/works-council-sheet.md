# What LifePete records — one page for the works council

> **Draft** (#352). Facts verified 2026-10; have counsel review before it is
> handed to a customer. Every claim below is checkable against the running
> product and the open source code, which is the point of it.

LifePete is a personal time tracker that an employer can read working-time
records from — not a monitoring tool with a privacy page. The difference is
structural, and this sheet says exactly where the line is so a works council
can check it rather than trust it.

## What the employer sees, in full

On **its own projects only**: each entry's start, end, duration and note;
absences as date, type and whole or half day; the contract a member holds on
one of its projects, its terms and its balance; timesheet status. That is the
entire list.

## What the employer can never see

- Whether anyone is working **right now** — the record carries finished
  entries only, no running flag, by decision and by code.
- Apps, websites, repositories, idle time, keystrokes or screenshots —
  **never built**, not "off by default".
- Flow scores, biometrics, calendar, the coach — the personal tracker's own
  data never crosses; no admin setting changes this.
- Personal projects, or that they exist.

Every employee can open the **"What _[employer]_ can see" page** at any time:
it is the employer's own read, narrowed to them — the actual data, not a
description of it.

## The four rules the code keeps

1. One person, one account, one timeline — joining never creates a work
   account, leaving loses nothing personal.
2. Every project has exactly one owner; what anyone sees follows from that.
3. Hours, not the person (the lists above).
4. Nothing is retroactive without consent — connecting an existing project
   shares history only from a day the employee chooses.

## Why this satisfies the law — and the council

- **CJEU C-55/18 (2019)**: member states must require "an objective,
  reliable and accessible system" recording daily working time. LifePete's
  record and compliance export are exactly that shape (per day: first
  start, last end, breaks, total, with rest-period and maximum-hours
  warnings derived on every read).
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
- **Approved months freeze**: once a timesheet is approved, every change
  inside the month is refused until a recorded, reasoned reopen — the
  record a council signs cannot drift silently. Every employer-side act
  (contract changes, approvals, reopens, admin-entered time) is in an
  audit log.
- **Retention**: Spain requires four years (art. 34.9 ET; fines for a
  missing or incorrect register are €751–7,500, LISOS art. 7.5 — the
  "€10,000 per worker" figure sometimes quoted comes from a bill the
  Congreso rejected in September 2025). Germany: two years (§16(2) ArbZG).
  LifePete keeps the record for the statutory period and the employee's
  departure or account deletion does not destroy it — nor extend what the
  employer sees.

## The line not crossed

The CNIL fined Amazon France Logistique €32 M over activity indicators; the
EU AI Act art. 5(1)(f) bans inferring emotions in the workplace. LifePete's
coach and biometrics exist **for the person only** and are structurally
unreachable by the employer — which is why this product can be signed off
where monitoring tools cannot.
