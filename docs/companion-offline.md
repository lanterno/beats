# The companion offline

> The companion opens and shows the timer, the projects and the day's
> sessions without a network, and a start, a stop, a session logged after
> the fact or a moved start made offline waits on the device and reaches
> the server when the network is back, at the time the person pressed.

The code is in `companion/lib/services/`: `offline_api.dart` (the client),
`offline_queue.dart` (a queued write and how a failure is judged),
`offline_view.dart` (the kept answers with the queue applied),
`local_store.dart` and `sqlite_store.dart` (where they are kept) and
`sync_story.dart` (what the app says about it). The API's half is the
idempotency middleware (`api/src/beats/api/middleware/idempotency.py`) and
the `expected` session a stop or an edit may name (#366).

The decisions below were made for #299 and are recorded so later work does
not re-litigate them.

---

## Decisions

1. **The device keeps the API's answers, not a model of its own.** Four
   reads are kept as the API returned them, as JSON keyed by request: the
   timer's status, the projects, one UTC day of sessions (the last 14 days)
   and a project's ledger. Offline, a read serves the kept answer with the
   writes still waiting applied on top, by the API's own rules: a start only
   when nothing runs, a stop only on the session it names, an edit only on
   the session as it was. Each step is a no-op when the answer already holds
   it, so a write that landed before it left the queue is never counted
   twice. The server stays the only record; nothing on the device is merged
   back into it.

2. **SQLite, through `sqflite`.** The companion is used on macOS, iOS and
   Android, and `sqflite` is a plugin on all three (macOS through Swift
   Package Manager). The queue needs what a key-value store does not give:
   a transaction to move a refused write out of the queue, and conditional
   single-statement updates for two engines over one file (decision 11).
   `shared_preferences` has neither, and each engine holds its own cached
   copy of it. `drift` would add code generation for three small tables of
   strings, and `sqflite_common_ffi` would mean shipping a SQLite library on
   the desktop. Where there is no plugin (Linux, Windows, the web) or the
   file will not open, a `MemoryStore` takes its place: offline works for
   the run and nothing outlives it.

3. **Four writes queue: a timer start, a stop, a session logged after the
   fact, and an edit of a session's times.** Those are what the timer and
   Today do. Everything else (the coach, settings, integrations) needs the
   network as before.

4. **Every write gets its idempotency key when it is made.** A random UUID,
   sent as `X-Client-Id`, the header the API's idempotency middleware keys
   its `mutation_log` on, and the one the web's `mutationQueue.ts` sends. The
   same key goes with every attempt, so a replay after a lost answer is
   answered from the API's record instead of applied twice. The middleware
   guards `/api/projects/{id}/start` and `/stop`, and `POST` and `PUT
   /api/beats/` from #366.

5. **The time is the one the person pressed.** A start and a stop carry
   `time`, a logged session its start and end, an edit its new times, all
   set when the write is made and stored with it in UTC. The API takes a
   client's times on all four, so when the replay happens changes nothing
   about when the session started or stopped.

6. **A write goes straight through only when the API was last reachable
   and nothing waits ahead of it.** Otherwise it waits at the back, so the
   API sees writes in the order they were made, and a stop never overtakes
   its start. A direct send that fails for want of a network is queued
   under the same key: as never sent when the request certainly did not
   leave (no address for the host, connection refused, no route), and
   otherwise as possibly sent, since it may have landed with its answer
   lost.

7. **The queue replays in order, one write at a time.** A write the API
   applies leaves the queue. A 4xx is final, except 401 and 403 (a pairing
   to mend; the write is still wanted), 408 and 429 (the server's pace) and
   409 `IDEMPOTENT_IN_PROGRESS` (the same write still running from another
   attempt): the write moves to a refused list kept on the device and the
   replay goes on to the next. A network failure, a 5xx or one of those
   exceptions stops the replay and keeps the write. A replay starts when a
   read gets through (the timer reads every 15 seconds) and when a write is
   queued while the API is reachable.

8. **A stop names the session it stops, and an edit the session it was made
   against.** The API refuses them with 409 `TIMER_CHANGED` or
   `BEAT_CHANGED` when the stored session is not that one, comparing
   instants to the millisecond, which is what a BSON date keeps. This is
   what keeps a timer started on another device while this one was offline
   running through the replay of this device's stop, and what keeps an edit
   from landing on a session changed elsewhere. An edit of a session
   deleted elsewhere is a 404 and is refused the same way. A start needs no
   precondition: the API already refuses one while a timer runs.

9. **Some writes are never queued.** Reopening a finished session (undoing
   a stop that has synced) could, replayed later, set it running beside a
   timer started elsewhere. The API's reopen refuses that since #376 — it
   makes the check a start makes — so the rule is now belt and braces
   rather than the only guard; a replayed reopen would be refused, not
   applied. A
   stop or an edit that names no session cannot be replayed safely. Offline,
   these are refused on the spot with a sentence saying a connection is
   needed.

10. **Undo and "Started earlier?" reach into the queue only for a write
    never attempted.** Undoing a stop that has not left the device removes
    it from the queue; moving the start of a timer whose start has not left
    rewrites the queued time. Once a request may have left, only the API
    knows whether it landed, and the person is told to wait for the sync.
    A start that has synced is moved by a queued edit naming it, which the
    following stop names in turn.

11. **Two engines, one file, one replayer.** The window and the menu bar
    popover are separate Flutter engines, each with its own connection to
    `offline.db` in the app's support directory. Only the window replays;
    the popover queues into the same file and reads how far the window has
    got. An attempt is counted in one statement before the request is sent,
    and cancelling or rewriting a write is one statement conditioned on no
    attempt, so neither engine can take back what the other is sending. Each
    connection waits up to three seconds for the other's write lock.

12. **Conflicts are shown, not resolved.** A refused write is listed on
    Today as what did not save and why ("Stopping Northwind at 10:30 wasn't
    saved. The timer had changed on another device.") until the person
    dismisses it. After every replay that lands or is refused, the timer is
    read afresh, so the screen shows what the server holds. Nothing is
    merged or retried behind the person's back.

13. **The app says where it stands, calmly.** The sidebar's status card
    reads *Synced*, *Offline* (with how many changes wait), *Syncing*, or
    *Can't reach the server* when nothing was kept to show. Its dot is leaf
    when all is saved, sun while changes wait (a wait that ends by itself is
    not trouble) and persimmon only for trouble. A phone's Today and the
    menu bar carry the same line when it is not *Synced*. Unpairing while
    changes wait says it will drop them.

14. **What the device keeps belongs to one pairing.** Pairing and unpairing
    clear the cache, the queue and the refused list: the writes of another
    pairing, another account's even (a Keychain wiped without unpairing),
    must never replay under a new token.

## Limits accepted

- The API keeps a write's record for 72 hours. A write that landed with its
  answer lost and is replayed after that is judged afresh: a stop or an edit
  is refused by the session it names, but a start or a logged session could
  be applied a second time.
- A replayed start or logged session is not checked against sessions made
  elsewhere meanwhile for overlap, as the API does not check one made online
  either. The log dialog refuses an overlap with what the device can see.
- On Linux, Windows and the web the queue lasts only as long as the run.
