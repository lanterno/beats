# Billing — what is left to build

One thing: **invoices**. There is no issue for it, because nobody has asked
for it yet; this file exists so that whoever does starts from the two facts
below rather than rediscovering them.

Everything else about billing is built and documented in
[docs/billing.md](../docs/billing.md) — clients, project billing, billable
overrides, billing budgets and report links. That file also lists what each
phase deliberately left out, which is a record of scope that was *cut*, not a
queue of work: those items are closed questions unless someone reopens them
on purpose.

## Invoices

**An invoice is a frozen copy of a month report's lines.** The arithmetic
already permits that, by a choice made deliberately in phase 1a: billing
rounds once per line (hours to 0.01, the amount to a whole minor unit) and
every total is a sum of its lines. So a stored invoice can quote a line
verbatim and still agree, to the minor unit, with what the month report shows
today. Had rounding happened once at the end, it could not.

**An "invoiced through" date would replace the month boundary in
`past_change`.** That check (`api/src/beats/domain/billing.py`) refuses a
write that changes figures before the 1st of the current month unless the
caller sends `rewrite_past`. The month boundary is a stand-in: the rule it is
really reaching for is "do not silently change what somebody has already been
invoiced for". Once invoices exist, that date is knowable, and the check can
say what it means.

Nothing else about invoices is decided — numbering, storage, PDF rendering,
tax, or whether they belong to this product at all rather than to the payment
machinery of [#345](https://github.com/lanterno/beats/issues/345).
