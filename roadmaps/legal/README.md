# Sales and legal material — drafts

Three documents the organisations epic owes
([#352](https://github.com/lanterno/beats/issues/352)). **All are drafts. None
has been reviewed by counsel, and none may reach a customer first.**

They exist so that counsel starts from the product's real architecture rather
than a generic template — one that would promise things the product
deliberately does not do, or miss the things it does better than the template
expects.

| File | Whose document it is | What it is for |
|------|---------------------|----------------|
| [dpa.md](dpa.md) | Ours to offer, the customer's to sign | The art. 28 GDPR processing agreement: the organisation controls its working-time records, we process them |
| [works-council-sheet.md](works-council-sheet.md) | Ours, handed to the customer | One page a works council can check rather than trust: what the employer sees, and what it can never see |
| [dpia-template.md](dpia-template.md) | The **customer's** document (art. 35) | Prefills the parts that describe LifePete so their DPO starts from facts |

## What blocks them

**Counsel review, and nothing else.** The work still owed — counsel, the
legal facts to re-check and when each was last checked, the re-read against
the product — is [#352](https://github.com/lanterno/beats/issues/352).

Every claim in the works-council sheet is meant to be checkable against the
running product and the open source. That is the point of it, and it is only
true while the claims match what the code does, so the drafts are re-read
whenever a decision changes what an organisation sees, reads or keeps. They
were last re-read against the code on 2026-11-02, through decision 33 of
[docs/organisations.md](../../docs/organisations.md).

## If you are editing these

Brackets mark what is filled in later, and stay until then. Most are the
customer's own; [dpa.md](dpa.md)'s header names its three kinds, the
operator's to fill and notes for counsel among them. A fact about the
product is not one of them: it is written in, as dpa.md's regions are.

Do not add a claim about what the product does without checking it against
the code and the files that describe it:
[docs/organisations.md](../../docs/organisations.md) for what an
organisation sees, [PRIVACY.md](../../PRIVACY.md) for who else does (the
operator, the hosting providers, the coach) and [DATA.md](../../DATA.md)
for what is stored. Where they disagree, the draft says what the code does
and the disagreement is an issue. A sheet whose purpose is "verify this
yourself" fails completely the first time a reader finds one sentence that
is not true.

When counsel signs these off, they stop being drafts and move to `docs/`.
