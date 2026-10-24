---
linear: unfiled
title: "The projects collection has no index"
team: AHM
project: lifepete
milestone: none
labels: [api, Improvement]
state: Todo
priority: 3
parent: none
---

`ensure_indexes` (`api/src/beats/infrastructure/database.py`) creates indexes
for eighteen collections. `projects` is not one of them, so every read of a
user's projects is a collection scan filtered by `user_id` — including
`GET /api/projects`, which the SPA, the companion, the daemon and the wall
clock all hit, and which the timer's status path goes through on every poll.

Harmless at today's scale: one person has tens of projects and the whole
collection is small. Worth fixing anyway, and worth fixing **before** AHM-74's
phase 2, which turns this read into "my projects, plus every organisation
project I am assigned to" across every tenant. Adding an index to a query is
easy; adding one to a query that has just become three times more complicated,
under a deadline, is not.

`{user_id: 1, archived: 1}` matches what `MongoProjectRepository.list` actually
asks for (`_find_many({"archived": archived})` under the store's `user_id`
filter).

Found while researching phase 2 ownership, not while chasing a slow query — so
measure before and after rather than assuming the shape.
