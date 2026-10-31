# Billing — what is not built

What is built is [docs/billing.md](../docs/billing.md): clients, project
billing, billable overrides, billing budgets and report links, with the
decisions behind each. That file also lists what each phase deliberately left
out, which is a decision rather than a plan and stays there.

One seed is a plan, and has no issue yet because nobody has asked for it:

## Invoices

An invoice is a frozen copy of a `period`'s lines. The arithmetic already
allows it: billing rounds once per line (hours to 0.01, the amount to a whole
minor unit) and every total is a sum of lines, so an invoice can quote a
line verbatim and still add up to the same figure the month report shows.

An "invoiced through" date would replace the month boundary in `past_change`
— the check that refuses a write changing figures before the 1st of the
current month without `rewrite_past`. Billing through a date somebody has
actually been invoiced for is the rule that check is really reaching for; the
month boundary stands in for it until invoices exist.
