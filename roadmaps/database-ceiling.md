# How full the database is, on a tier with a ceiling

**Blocked on one decision: where the control plane learns the cluster's
storage limit.** Everything else it needs is already kept.

Capacity says how fast the database grows
([docs/backoffice.md](../docs/backoffice.md), § The pages, *Capacity and
cost*), not how far it is from full. The mock
(`docs/backoffice-mock/source/Capacity.dc.html`) says "the cluster is sized
by hand, so there is no ceiling to measure against", which is true of a
dedicated Atlas tier and false of the one production runs on: Atlas's free
tier allows 0.5 GB of "uncompressed BSON documents stored in all collections,
plus the bytes stored in their associated indexes"
([Atlas free cluster limits](https://www.mongodb.com/docs/atlas/reference/free-shared-limitations/)).
The page was built without that sentence, and without a limit in its place.
What Atlas does to a cluster past the limit is not written on that page;
find out before step 3 below, since it decides how early the warning must
come.

## What is there already

- **The figure the limit is measured against has a history.** The free tier
  counts the documents uncompressed, with their indexes; the page draws the
  size on disk, which is compressed and reads lower. The job runner keeps
  both, per collection and per UTC day, in `database_sizes`
  (`data_bytes`, `index_bytes` and `storage_bytes`;
  `api/src/beats/infrastructure/database_sizes.py`), and `$collStats` serves
  them live.
- **A tile with a limit beside it** — the connections, "N of 500 allowed" —
  whose limit comes from the server itself (`serverStatus`). Storage has no
  such answer from the server, which is the whole problem.

## What must not happen

- **A limit written into the page or the API as 512 MB.** The cluster is
  resized by hand in Atlas, and a constant goes silently wrong the day it is.
- **A percentage of the size on disk.** It is the wrong figure: compressed,
  it reads lower than what the limit counts.
- **An invented figure when the source does not answer.** Say so, the way the
  connections tile does.

## Work

1. **Decide where the limit comes from.** The candidates: the Atlas Admin
   API, which knows the tier but needs an Atlas API key on the operator
   deployment, a credential the control plane does not hold today; or a value
   Terraform sets (the shape of `OPERATOR_API_MAX_INSTANCES`), changed in the
   same edit as the tier, which only works while the tier is itself in
   Terraform, and it is not. Write the decision into docs/backoffice.md.
2. **Serve and draw it.** The uncompressed total and the limit on
   `GET /api/operator/capacity`; the database tile says how much of the limit
   is used, and the headline when the pace reaches it.
3. **Decide who hears about it before it is reached**: a row on Today's
   attention list, an alert that pages, or both. Check first what Atlas's own
   alerts already send for a free cluster, so the operator is not told twice.
