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
yet (2026-10-31); what it shows meanwhile is in
[docs/pricing.md § The beta](../docs/pricing.md#the-beta). **Start when the
end of the beta is decided** — and the date chosen has to leave room for
the build, because the grace period an organisation past the free seats
then gets is time to pay: taking a payment (the provider, tax, invoices)
has to work the day that period begins, and the read-only gate the day it
ends. An organisation cannot go read-only for not paying when there was
never a way to pay.

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
   priced in euros and sold to EU businesses. That means VAT, and how it
   falls turns first on **where the seller is established**, which nothing
   here says yet ([legal/dpa.md](legal/dpa.md) still names the processor
   `[operator entity]`). For a seller in the EU, a business in another
   member state that gives a valid VAT ID is reverse-charged; a customer in
   the seller's own member state, business or not, pays the seller's VAT;
   and a customer who gives no VAT ID may be treated as a consumer, charged
   their own country's rate (past €10,000 a year of such sales) on evidence
   of where they are, through the one-stop shop's Union scheme. A seller
   outside the EU has every EU business reverse-charged and declares the
   rest through the non-Union scheme. Most providers will do this, and the
   decision is whether to take theirs or carry it — but it is a decision,
   not a detail.
3. **Invoices.** Ours, to an organisation; a freelancer's to a client is
   [billing.md](billing.md), issued by the freelancer in their own series.
   Across the EU an invoice is a legal document with a sequential number
   (art. 226 of the VAT Directive) and a retention period each member
   state sets (art. 247). Note the shape this repeats: **an invoice is a
   frozen derived figure**, like the approved month of decision 23 in
   [docs/organisations.md](../docs/organisations.md) — computed once,
   stored, and never silently recomputed when the inputs move afterwards.
   That decision is already made once in this codebase, with its reasoning,
   and the second one should read it rather than rediscover it. **Copy the
   freeze, not the way back:** a reopened month drops its frozen figures
   and is approved afresh, but an issued invoice is never reopened. A
   credit note that cites it corrects it, under a number of its own
   (art. 219), and the original is kept. Where the seller is established
   also decides the invoice's format. A member state's e-invoicing mandate
   binds sellers established there, for business customers there —
   Belgium's and Poland's since 2026, France's from 2026-09 and Germany's
   from 2027, both phased by size — and from 2030-07-01 (ViDA) an invoice
   to a business in another member state must be a structured e-invoice
   too, to EN 16931. A PDF is none of these. Whether a provider issues
   them is part of choosing it (piece 1); if it does, it stores them and
   nothing here does, but unless it sells in its own name as merchant of
   record, keeping them is still our duty (art. 244).
4. **Dunning.** Only its end state is decided
   ([docs/pricing.md § The beta](../docs/pricing.md#the-beta)). The retries,
   how long a failed payment waits before that end state, and who is told
   are not — and the notice and grace period there are for the end of the
   beta, not a grace period after a failed renewal.

## Counting the seats

[docs/pricing.md § What a seat is](../docs/pricing.md#what-a-seat-is)
defines a seat. Two things that definition implies for the code:

- the count at this moment is derived from `org_members` and
  `org_assignments`; the count over a past period is not. Each keeps one
  document per member, or per member and project, reopened in place
  ([docs/organisations.md § Data model](../docs/organisations.md#data-model)):
  rejoining or reassigning overwrites `joined_at` or `assigned_at` and
  clears `left_at` or `ended_at`, and a role change — which decides
  whether a viewer is free — is stored with no date. The history is only
  in `org_audit`, written after each change rather than with it, so a
  crash between the two loses the event. Billing a period needs history
  of its own — seat intervals written with the change, or the count
  pushed to the provider as it moves — not those dates;
- **a seat begins at the assignment, never at the invitation** — at
  `assigned_at`, and on a connected project never at `shared_from`, which
  a connect may set in the past. The competitors' fine print is where
  `docs/pricing.md` chose to differ, so the implementation is where that
  promise is kept or quietly lost.

## The round trip

The provider calls us, and no third party's server has before. Its webhook
is a public path, but not on the terms the comment on `PUBLIC_PREFIXES` in
`api/src/server.py` gives: a signature is its whole authorisation and it
serves nothing, so that comment gains a line saying so. It belongs to the
public deployment; the operator's sits behind IAP, which the provider cannot
pass ([backoffice.md](backoffice.md)). It checks the signature, records the
event's id so a second delivery does nothing, and assumes no order: Stripe,
for one, retries a delivery for three days and does not promise the order
events arrive in. Stripe also advises answering before processing, which
assumes a process that keeps running. On Cloud Run that is a task left
after the response, which is not reliably finished
([server-push.md](server-push.md)), so the handler makes its few writes and
then answers.

Whether an organisation is read-only is a field stored here, read by the one
gate below, never a call to the provider inside a request: an outage at the
provider refuses nobody. A seat change never waits on the provider either.
`org_members` is right and the invoice follows it, so assigning or removing
someone cannot fail because the provider is down; the new count reaches the
provider from a queued job or from the reconciliation. Both need something
to run them, and nothing does: `terraform/` schedules nothing today.
[backoffice.md](backoffice.md) (#424) plans a Cloud Run Job on a Cloud
Scheduler trigger, and [server-push.md](server-push.md) (#298) cannot send
at 07:00 without a scheduler either. The reconciliation runs on whichever of
those lands first, not on a third.

## What must not happen

- **Never delete an organisation's record for non-payment.** It is a
  working-time record the organisation may be bound by law to keep
  (decision 30 in [docs/organisations.md](../docs/organisations.md)), and
  one its members and a works council rely on. Read-only has to keep the
  record **readable and exportable** — the CSVs and `/record` included —
  or "read-only, never deletion" means nothing.
- **An invoice outlives the organisation and the person who paid it.** It
  is the seller's record, kept for the seller's statutory period (art. 247
  of the VAT Directive leaves that to each member state: eight years in
  Germany since 2025, § 14b UStG), not for the organisation's
  `retention_years`, which can be one year. Three deletions that exist
  would take it if it were stored like the rest: deleting an organisation
  (decision 29: everything that was the organisation's goes), the
  retention purge (decision 30, which already expires the frozen months
  piece 3 likens an invoice to), and erasing an account, whose sweep in
  `api/src/beats/infrastructure/erasure.py` deletes every document holding
  the person's `user_id`, in every collection there is. So neither an
  invoice nor the subscription holds a `user_id`, none of the three
  touches them, and deleting an organisation cancels its subscription at
  the provider before the wipe. PRIVACY.md and DATA.md promise to delete
  every document keyed to a user; the change that stores the first invoice
  names it there as an exception.
- **Billing state must never be a reason a person is refused their own
  data.** Rule 1: one person, one account, one timeline. Whether an
  organisation has paid is between us and the organisation; a member's own
  entries, exports and account are untouched by it, including on a project
  that organisation owns.
- **No card data in Mongo.** The provider holds the instrument; we hold a
  customer id and a subscription id. This is not a thing to be clever about.
- **The provider is a new recipient, so PRIVACY.md changes first.** Its
  list of who can see your data ends *"No one else. Beats does not sell,
  share, or syndicate your data"*, and a payment provider is someone else:
  it holds what billing needs, a billing contact, an address and a VAT ID.
  Name it in [PRIVACY.md](../PRIVACY.md) before the release that sends it
  anything, as [server-push.md](server-push.md) and
  [organisation_sso.md](organisation_sso.md) do for theirs. What Mongo
  keeps of it goes into [DATA.md](../DATA.md), the catalogue of every
  field, in the same change.
- **No organisation reaches the provider before it goes past the free
  seats.** A small team inside them owes nothing, so it has no customer
  record there either, not merely no invoice: the real zero of the first
  piece, above, is a zero for the provider too.
- **Do not let the subscription become a second source of truth for
  membership.** The provider knows a number; `org_members` knows who. If the
  two disagree the organisation is right and the invoice is wrong, and the
  reconciliation has to run that way round.
- **Read-only must be one gate, in one place**, never a flag checked per
  route: the shape #342 chose for its attestation, and #340 for money on
  the billing collections' boundary. Two routers share
  `/api/organisations` (`routers/organisations.py` and
  `routers/employment.py`) and neither has a router-level dependency
  today, so the one check goes on both. It refuses every write by
  default — a route added later is read-only because of where the check
  sits, not because somebody remembered — and its exemptions are listed
  beside it: leaving (`POST /{id}/leave`), closing and deleting (decision
  29), and paying. Without them an unpaid organisation is a trap, not a
  degraded state. `POST /join` names no organisation in its path, so a
  gate keyed on the path misses it.
- **A deployment that names no payment provider takes no money and makes
  nothing read-only.** The repository is MIT and `compose.selfhost.yml`
  runs the same API as lifepete.com; a gate that fired on "past the free
  tier and no subscription" would lock every larger organisation on a
  self-hosted box, with nothing it could pay. Collecting is something a
  deployment turns on, as single sign-on is off unless `OIDC_PROVIDERS`
  names a provider (`api/src/beats/settings.py`), and with it off no
  organisation is ever read-only for payment.
