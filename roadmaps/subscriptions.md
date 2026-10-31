# Taking the money

The first money that flows **to** us. Issue **#345**: an organisation pays
per seat for the record it reads.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31.
What to charge is decided and written down — [docs/pricing.md](../docs/pricing.md),
2026-10-28: the price, what a seat is, who is free, and what happens to an
organisation that does not pay. **Read it first; none of it is repeated
here.** What is left is collecting it, and a payment provider, tax,
invoices and dunning are not an organisations feature in any sense.

**On hold, deliberately.** The owner expects the beta to run for some months
yet (2026-10-31). Everything is free during it, shown as a 100 % discount
with the real price struck through, so nobody is building on a price they
have not seen.

---

## What exists

Nothing. There is no payment code anywhere in the repo: no provider, no
customer id, no invoice, no subscription state, no webhook from a processor.
The marketing page (`ui/client/pages/homepage/HomePage.tsx`) shows the price
struck through, and that is the whole of it.

That is the honest starting point, and it is why `docs/pricing.md` closes by
saying collecting the money is its own project rather than a phase of the
epic that priced it.

## The four pieces, in the order they bite

1. **A provider.** Nothing obliges a choice; Stripe is the obvious one and
   `docs/pricing.md` deliberately does not say so. What the choice has to
   carry: per-seat subscriptions with a count that changes mid-period,
   annual and monthly at different unit prices, and a free tier that is a
   real zero rather than an invoice for nothing.
2. **Tax, which is the part that gets underestimated.** The product is
   priced in euros and sold to EU businesses. That means VAT: the one-stop
   shop for consumers, reverse charge for a business that gives a valid VAT
   ID, evidence of where the customer is, and the rate per country. Most
   providers will do this, and the decision is whether to take theirs or
   carry it — but it is a decision, not a detail.
3. **Invoices.** In much of the EU an invoice is a legal document with
   sequential numbering and a retention period of its own. Note the shape
   this repeats: **an invoice is a frozen derived figure**, exactly like the
   approved month of decision 23 — computed once, stored, and never silently
   recomputed when the inputs move afterwards. That decision is already made
   once in this codebase, with its reasoning, and the second one should read
   it rather than rediscover it.
4. **Dunning**, whose outcome is already decided: an organisation that does
   not pay goes **read-only, never deleted**.

## Counting the seats

`docs/pricing.md` defines a seat precisely — an active member with an
assignment, viewers free, nobody counted before they join. Two things that
definition implies for the code:

- the count is derived from `org_members` and `org_assignments`, which
  already carry the dates (`joined_at`, `left_at`, `assigned_at`,
  `ended_at`), so a mid-period change is answerable without new state;
- **a seat begins at the assignment, never at the invitation.** The
  competitors' fine print is where `docs/pricing.md` chose to differ, so the
  implementation is where that promise is kept or quietly lost.

## What must not happen

- **Never delete an organisation's record for non-payment.** It is a
  working-time record its members and a works council may be bound to keep.
  Read-only has to keep the record **readable and exportable** — the CSVs
  and `/record` included — or "read-only, never deletion" means nothing.
- **Billing state must never be a reason a person is refused their own
  data.** Rule 1: one person, one account, one timeline. Whether an
  organisation has paid is between us and the organisation; a member's own
  entries, exports and account are untouched by it, including on a project
  that organisation owns.
- **No card data in Mongo.** The provider holds the instrument; we hold a
  customer id and a subscription id. This is not a thing to be clever about.
- **Do not let the subscription become a second source of truth for
  membership.** The provider knows a number; `org_members` knows who. If the
  two disagree the organisation is right and the invoice is wrong, and the
  reconciliation has to run that way round.
- **Read-only must be one gate, in one place** — the shape #342 and #340
  both settled on: a dependency on the organisation router, never a flag
  checked per route. A route added later must be read-only by default
  because of where the check sits, not because somebody remembered.
