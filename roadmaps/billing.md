# Billing — what is left to build

One unbuilt idea: **invoices**. There is no issue for it, because nobody
has asked for it yet; this file exists so that whoever does starts from the
two facts below rather than rediscovering them.

Everything else about billing is built and documented in
[docs/billing.md](../docs/billing.md) — clients, project billing, billable
overrides, billing budgets and report links. That file also lists what each
phase deliberately left out, which is a record of scope that was *cut*, not a
queue of work: those items are closed questions unless someone reopens them
on purpose. One was deferred rather than cut, and belongs to the
organisations epic: an organisation's project is billed by nobody
(`ORGANISATION_PROJECT`, raised in `api/src/beats/domain/billing_service.py`),
and money on one is [#340](https://github.com/lanterno/beats/issues/340),
with its reasoning in [organisations.md](organisations.md).

## Invoices

**An invoice is a frozen copy of a month report's lines.** The arithmetic
already permits that, by a choice made deliberately in phase 1a:
[decision 7](../docs/billing.md#decisions) rounds each line once and makes
every total a sum of lines. So a stored invoice can quote its lines
verbatim, its total is the sum of what it quotes, and on the day it is
issued it agrees with the month report to the minor unit. Had rounding
happened once at the end, its lines would not always add up to its total.
Nothing keeps the invoice and the report agreeing afterwards: the report is
worked out on every read, and an edited entry, an override, or a rate
changed with `rewrite_past` moves it while the invoice keeps what it quoted.

Storing one would make it the first stored billing figure, frozen in the
way the approved month of [decision 23](../docs/organisations.md) is. That
decision records that no billing figure is stored, and
[PRIVACY.md](../PRIVACY.md) and [DATA.md](../DATA.md) tell users the same
of what each month comes to. Read decision 23's reasoning before designing
the invoice ([subscriptions.md](subscriptions.md) sends #345's invoices to
the same precedent), and do not store the first one while those three files
still say no such figure is stored.

**An "invoiced through" date would replace the month boundary of
[*the closed past*](../docs/billing.md#the-closed-past)**, which says which
writes need `rewrite_past` and already allows for that date. The boundary
comes from one place, `BillingService._month_start`
(`api/src/beats/domain/billing_service.py`), and `past_change`,
`link_change` and `marked_change` in `domain/billing.py` take it as an
argument; so does the currency check on a move to another client. It is a
stand-in: the rule it is really reaching for is "do not silently change
what somebody has already been invoiced for". Once invoices exist, that
date is knowable, and the gate can say what it means.

The date is a client's, not the account's: an invoice goes to one client,
and each client is invoiced on its own day. A write is gated from the date
of every client whose figures it moves — on a project's move, both, as
`link_change` already reads the old terms and the new together. An entry is
held against that date by its local day in the timezone the invoice was
issued in, as a report link keeps the owner's (1c's decision 2): the gate
buckets by the request's timezone today, and a stored date read that way
can put a beat near midnight outside the invoice it is on. And a stored
date says only what was invoiced in LifePete. A client invoiced outside it
— every client today — has none and keeps the 1st of the month: replacing
the boundary outright would leave its past ungated, which decision 11 of
[docs/billing.md](../docs/billing.md) forbids.

One question about the refusal itself (409 `RETROACTIVE_CHANGE`) is already
open: [#337](https://github.com/lanterno/beats/issues/337), a decision, on
whether it should also name the report links that show the months a write
rewrites. A report link backs an invoice period (1c's decision 2 in
[docs/billing.md](../docs/billing.md)), so answer it with invoices in view.

Nothing else about invoices is decided — numbering, storage, PDF rendering,
tax, or whether they belong to this product at all. They are not
[#345](https://github.com/lanterno/beats/issues/345)'s: the invoices in
[subscriptions.md](subscriptions.md) are LifePete's own, to an organisation
for its seats, and these would be a freelancer's, to their own client. Each
issuer keeps its own numbering series, and a payment provider set up to
collect LifePete's price cannot issue them. The two never share a series or
a collection: a client, a rate and an amount stay in the freelancer's own
collections (decision 2 of [docs/billing.md](../docs/billing.md)), on the
side of [docs/backoffice.md](../docs/backoffice.md)'s line the operator never sees.
