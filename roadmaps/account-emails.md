# Several addresses on one account

One account keeps **one main address** — the one it is known and written to
by — and **any number of verified others** beside it. Nothing is ever matched
against an address nobody has proved they hold.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31.
Verified email domains for joining an organisation (#341) is what asked for
it, and it is the smaller half: the account model is the work, and it is not
an organisations feature. Decided then too: **the rule is to match a
verified address**, never a string somebody typed.

---

## Why it is wanted, beyond #341

An invitation is addressed to an address, and only the account holding that
address can take it (decision 11, `_open_invite` in
`api/src/beats/domain/organisations.py`). Today "holding" means the account's
single `email` field. So **an invitation to a work address cannot be taken by
an account that signed up with a personal one** — which is the ordinary case,
not an edge: people sign up with their own address and are invited at work.
There is no way round it today except changing the account's address.

So this is already a friction with no feature attached to it. #341 is the
second consumer, not the first.

## What is there now

`User.email` is a single required string (`domain/models.py`), unique by
index (`infrastructure/database.py`: `users.create_index("email", unique=True)`).
Five things read it, and they want different things:

| Reader | What it wants |
|---|---|
| `routers/auth.py` registration | **Anti-takeover**: an address that already has a passkey is a 409, because matching an existing account by email is how one would be stolen |
| `auth/webauthn.py` (`user_name`) | A **label** for the authenticator's own UI |
| `routers/account.py` (`/me`) | What to **show** the person |
| `auth/sso_accounts.py` (`sso_email_for`) | What to **name a new account** — nothing is ever matched by email here, deliberately |
| `domain/organisations.py` (`_identity`) | What the organisation **knew them by**, stamped onto `org_members` at joining |

Only the first is an identity check, and it is a *refusal*, not a match.
That is the property to keep.

## The shape, and the one real choice

`User.email` **stays** as the main address: the unique index stays, every
reader above keeps working, and the change is additive. What is new is the
set of other addresses, and where it lives is the decision:

1. **A collection, `account_emails`, unique on `address`** — each row an
   address, the account it belongs to, and `verified_at`. Recommended: one
   index enforces "no address belongs to two accounts" across the main and
   the others at once, and lookup *by address* — what an invite does on every
   join — is the indexed hot path rather than a scan of an array field.
2. An array on the user. Simpler to read with the account, but Mongo cannot
   enforce uniqueness across an array field and a scalar field together, so
   the rule would live only in a write-time check, with the race left open.

Either way the main address is mirrored, not moved: two sources for one fact
is the cost of (1), and it is worth naming in whichever is chosen.

## Verification is where the no-email rule gets revisited

The API sends no email (decision 11), on purpose. A verified address needs a
message sent to it, so this is the work that changes that — **narrowly**:

- a transactional verification message, and nothing else;
- it does **not** reopen invitations by email (decision 11's reasoning is
  about handing out the way in, and that is unchanged);
- it does **not** make email a notification channel. That question is already
  answered the other way: #351's channel is server push
  ([server-push.md](server-push.md)).

Until that exists, nothing here can be built, and #341 least of all: a domain
rule over unverified addresses hands memberships to whoever registers an
address, which is the exact hole decision 11 closed, at organisation scale.

## What must not happen

- **Never match an unverified address** to an invitation, a domain rule, or
  anything else. An unverified address is a label.
- **An address is not a door.** WebAuthn passkeys and OIDC identities are the
  two ways in, and adding an address must not quietly become a third —
  no "sign in with your email" falls out of this.
- **Two accounts must never verify the same address**, and the check has to
  cover the main address as well as the others, which is the whole argument
  for (1) above.
- **Removing the last verified address** needs the guard `unlink` already
  applies to the last credential (`auth/sso_accounts.py`): an account must
  not be left with no way for anyone to reach its owner.
- **Changing the main address must not rewrite history.** `org_members.email`
  is what the organisation *knew the person by* when they joined, kept after
  erasure as part of its record (decision 3). It is a snapshot, not a
  reference, and a later address change leaves it alone.
