---
linear: unfiled
title: "Decide what happens when the employer's contract terms differ from the employee's"
team: AHM
project: lifepete
milestone: none
labels: [api, ui, decision]
state: Backlog
priority: 3
parent: AHM-74
---

From AHM-74's decisions, and left entirely open there:

> Disagreeing about the contract. If the employer's terms differ from what the
> employee had, who wins, and how is the disagreement shown?

Gates phase 3, which makes contract terms employer-owned.

## The concrete case

Someone tracks their day job as a personal project today, with a contract they
entered themselves: 80%, from March, Zurich holidays, an opening balance of
+12 h. They join their employer's organisation and connect the project. The
employer's record says 100% from January, and says nothing about an opening
balance.

Their overtime balance — a figure they may have been relying on for months —
now changes. `domain/contracts.py` recomputes it from the terms on every read,
so the moment the terms are replaced, every week in the ledger moves.

## What has to be answered

- Does connecting a project overwrite the personal contract, keep both, or
  refuse until someone reconciles them?
- Is the employee's opening balance preserved, discarded, or turned into a
  balance adjustment on the connection date?
- What does the project page show while the two disagree?
- Can an employee dispute a term, or only see it?

Note that the epic's own principle — "nothing is retroactive without consent"
— already points at an answer: an employer's terms should not silently rewrite
history the employee recorded before joining. The existing
`RETROACTIVE_CHANGE` gate in billing is the shape of a precedent.
