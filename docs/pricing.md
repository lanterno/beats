# Pricing

> LifePete is free for a person. An organisation pays per seat for the record
> it reads. During the beta everything is free — a 100% discount, shown as one,
> so the price is known before it is charged.

Decided 2026-10-28, closing the one pricing decision the organisations epic
left open ([organisations-roadmap.md](organisations-roadmap.md) § Decisions
still open). This file records the decision and the market it was priced
against; the payment machinery that would collect it is deliberately not
built — see *What this does not decide*, below.

## The model

- **Personal use is free.** Joining or leaving an organisation never changes
  the person's plan — the epic fixed that before any price existed.
- **An organisation pays €8 per seat per month billed annually, €10 billed
  monthly.** Priced in euros: the sales story is EU working-time law.
- **Free up to 5 seats.** A small team, a pilot, or a works council evaluating
  the product starts without procurement.
- **Single sign-on is included in the paid tier.** Most of the market parks
  SSO in its top tier; for a product whose pitch is privacy and compliance,
  charging extra for secure sign-in would undercut the story it sells.
  SCIM, when it exists (#343), belongs to a later sales-led enterprise tier.
- **One subscription per organisation.** A person in three organisations is
  three seats, each paid by its organisation, as Notion bills each workspace.

## What a seat is

A seat is an **active member with a project assignment** — someone whose hours
the organisation reads, or who runs the organisation. Specifically:

- Owners, admins, managers and members with an active assignment count.
- **Viewers are free**: an accountant or a works council seat reads the record
  and changes nothing; charging for oversight is off-brand.
- **Contractors count when assigned.** The organisation reads their hours; the
  record is what it pays for.
- Invited-but-not-joined, pending join requests, and members who left or were
  removed do not count. A seat begins when the assignment does — billing on
  approval, never on invitation.

## The beta

Everything is free during the beta, framed as a **100% beta discount with the
real price shown struck through**, so no one builds on a price they have not
seen. When the beta ends:

- organisations over 5 seats get **notice and a grace period (60 days)**;
- an organisation that does not pay degrades to **read-only — never deletion**.
  Its working-time record is a legal record: it stays readable and exportable,
  and members' own data is theirs regardless (rule 1).

## The market it was priced against

Checked on the vendors' own pricing pages, October 2026 (the roadmap warned
the earlier figures came from aggregators):

| Product | Free tier | Team tier (annual, /seat/mo) | SSO gated at |
|---|---|---|---|
| Toggl Track | up to 3 users | Starter $9 ($12 monthly) | Premium ($16) |
| Clockify | up to 5 users | Pro $7.99 ($9.99 monthly) | Enterprise ($11.99) |
| Harvest | 1 seat, 2 projects | Teams $9 ($11 monthly) | Enterprise ($14) |
| Everhour | up to 5 seats | Team $8.50 ($10 monthly), 5-seat min | included |
| Hubstaff | trial only | Team $10 ($12 monthly) | Enterprise ($25) |
| Timing | trial only | Connect ~$14–16 | not offered |
| absence.io | trial only | Pro €4.99 (time tracking + SSO) | included |
| Factorial | none | "from $8", quote-based | not public |

The usable team tier clusters at **$8–12/seat/month annual**. €8 sits in the
cluster, above Clockify's cheap end — LifePete is not competing on cheap — and
below the Hubstaff-style monitoring tools whose model it exists to refuse.
Seat-counting fine print is where competitors bite (Clockify bills every
invited user, Everhour bills a 5-seat minimum, Harvest adds a usage meter);
the seat definition above is chosen to have none.

## What this does not decide

Collecting the money — a payment provider, tax, invoices, dunning — is the
first money flowing *to* us and is its own project, as the roadmap says
(#345). Nothing here obliges a provider choice. Organisation-side money
(rates, costs, budgets inside an organisation) is a separate, undesigned
space guarded by its own rule — seeing money is a permission, not a role
(#340) — and this file prices seats, not that.
