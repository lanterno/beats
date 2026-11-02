# Several addresses on one account

One account keeps **one main address** — the one it is known and written to
by — and **any number of verified others** beside it. Nothing is ever matched
against an address nobody has proved they hold.

Split out of [roadmaps/organisations.md](organisations.md) on 2026-10-31.
Verified email domains for joining an organisation (#341) is what asked for
it, and it is the smaller half: the account model is the work, and it is not
an organisations feature.

**Decided 2026-10-31 by the owner**, answering #341: the shape above, one
main address with verified others beside it, and **the rule is to match a
verified address**, never a string somebody typed. Where the others are
stored is still open; the recommendation is below.

---

## Why it is wanted, beyond #341

An invitation is addressed to an address, and only the account holding that
address can take it (decision 11, `_open_invite` in
`api/src/beats/domain/organisations.py`). Today "holding" means the account's
single `email` field. So **an invitation to a work address cannot be taken by
an account that signed up with a personal one** — which is the ordinary case,
not an edge: people sign up with their own address and are invited at work.
Nothing gets round it from the invitee's side: no route changes an account's
address once the account exists. The ways round it are the inviter's —
address the invite to the account's own address instead, or send an invite
link, which carries no address and so is tied to nobody (decision 11).

So this is already a friction with no feature attached to it. #341 is the
second consumer, not the first.

## What is there now

`User.email` is a single required string (`domain/models.py`), unique by
index (`infrastructure/database.py`: `users.create_index("email", unique=True)`).
Five things in the API use it, and they want different things:

| Where | What it wants |
|---|---|
| `routers/auth.py` registration | **Anti-takeover**: an address that already has a passkey is a 409, because matching an existing account by email is how one would be stolen |
| `auth/webauthn.py` (`user_name`) | A **label** for the authenticator's own UI |
| `routers/account.py` (`/me`) | What to **show** the person |
| `auth/sso_accounts.py` (`sso_email_for`) | What to **name a new account** — it writes the field, with a synthetic `@sso.invalid` address no mail can reach; nothing is ever matched by email here, deliberately |
| `domain/organisations.py` (`_identity`) | What the organisation **knew them by**, stamped onto `org_members` at joining |

Only the first is an identity check, and it is a *refusal*, not a match.
That is the property to keep.

The authenticator's label does not follow a change. `user_name`, and
`user_display_name` while the account has no display name, are written into
each passkey when it is made. A passkey is found by its credential id, never
by the address, so a changed main address breaks no sign-in, but the
passkeys already made keep showing the old one. The web app can ask the
passkey provider to update them with
`PublicKeyCredential.signalCurrentUserDetails`, after the change and at each
sign-in. Firefox does not have it, and a provider may ignore it, so the old
address can stay in somebody's passkey list.

Three more hold it outside those five. The session token carries it as an
`email` claim (`auth/session.py`), copied forward on every refresh and read
by nothing: drop it, rather than keep it in step with a main address that
can change. The operator finds an account by it to erase it
(`scripts/erase_account.py`, an exact match on `users.email`), because
PRIVACY.md and DATA.md have deletion asked for "from the address on your
account"; and the back office will look accounts up by it too, though
regardless of case, since sign-up stores an address as typed
([backoffice.md](backoffice.md), *Accounts*). Which address those two match
once there are several — the main only, or any verified one too — is this
work's to settle, and PRIVACY.md's wording with it. An added address not
yet verified is never one of them.

## The shape, and the one real choice

`User.email` **stays** as the main address: the unique index stays,
everything above keeps working, and the change is additive. What is new is
the set of other addresses, and where it lives is the decision:

1. **A collection, `account_emails`, unique on `address` among verified
   rows** — each row an address, the account it belongs to, and
   `verified_at`; the index is partial, over the rows that carry it.
   Recommended: an address somebody has only asked to add then sits beside
   the verified ones and holds nothing, and each address keeps its whole
   life on one row. The account is `user_id`, the string id the account's
   other collections keep: erasure (`infrastructure/erasure.py`) deletes by
   `user_id` in every collection there is, so a row keyed any other way
   outlives its account and keeps its address claimed under the unique
   index, where nobody can verify it again. `DATA.md` lists the collection
   in the same change, since its *Deletion* section covers the collections
   it lists.
2. An array on the user. Simpler to read with the account, and a unique
   multikey index keeps an address to one account and serves lookup by
   address, as it does for `identities` (`infrastructure/database.py`). But
   a partial filter picks documents, not array elements, so that index would
   hold pending addresses too — whoever asks first keeps an address from its
   holder — unless pending ones live somewhere else.

Either way the main address is mirrored, not moved: `users.email` keeps it,
and a copy sits with the others, which is what lets one index cover the
main and the others together. Two sources for one fact is the cost. Under
(2) one write to the user keeps them in step; under (1) they sit in two
collections that no single write keeps in step, and whoever builds it names
which of the two wins when they disagree.

## Verification is where the no-email rule gets revisited

The API sends no email (decision 11), on purpose. A verified address needs a
message sent to it, so this is the work that changes that — **narrowly**:

- a transactional verification message, and nothing else;
- it does **not** reopen invitations by email (decision 11's reasoning is
  about handing out the way in, and that is unchanged);
- it does **not** make email a notification channel. That question is already
  answered the other way: #351's channel is server push
  ([server-push.md](server-push.md)).

The message needs a sender no deployment has. The hosted API cannot deliver
mail itself — Google Cloud blocks outbound port 25 — so it sends through a
mail provider, a third party that sees the address and the message. That
breaks a promise PRIVACY.md makes in so many words, that LifePete *"sends no
email and, since it cannot verify an email address, never hands the way in
to whoever holds one"*: **change PRIVACY.md before the release that sends
one**, as [server-push.md](server-push.md) has it for push, and name the
provider there. Decision 11 in
[docs/organisations.md](../docs/organisations.md), which 27 and 29 cite,
says the API sends no email; that release amends it.

A sender is optional, as single sign-on's providers are (`OIDC_PROVIDERS`).
A deployment without one — the self-hosted stack, as it stands — verifies
nothing, and #341's domain rule is not offered there.

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
  cover the main address as well as the others — the mirror does that in
  either shape. An address only asked for must not stop its holder verifying
  it, which is the argument for (1) above.
- **Removing the last verified address** needs the guard `unlink` already
  applies to the last credential (`auth/sso_accounts.py`): an account must
  not be left with no way for anyone to reach its owner.
- **Changing the main address must not rewrite history.** `org_members.email`
  is what the organisation *knew the person by* when they joined, kept after
  erasure as part of its record (decision 3). It is a snapshot, not a
  reference, and a later address change leaves it alone.
