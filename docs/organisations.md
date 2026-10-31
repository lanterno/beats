# Organisations

> LifePete is a personal tracker: one person, their projects, their time. An
> **organisation** is a party that owns projects and reads the hours on them
> — an employer, a team, a client big enough to want its own view. A person
> has **one account and one timeline**; joining an organisation adds its
> projects to that timeline, marked, and shows the organisation the hours on
> them and nothing else.

This is what the organisations epic (#353) has built: the foundations (stage
2, decisions 1–20), employment (stage 3) and scale (stage 4, decisions 21–30),
and three settled after (31–33). It records the decisions the build rests on,
so later work does not re-litigate them. Stage 1, clients and billing, is in
[billing.md](billing.md). What is not built yet, and why each piece waits, is
in [roadmaps/organisations.md](../roadmaps/organisations.md).

---

## The four rules

Everything below keeps these, and they are the reason the architecture has
the shape it has.

1. **One person, one account, one timeline.** Joining never creates a second
   account, never moves data, never needs another login. Leaving every
   organisation leaves the account as it was.
2. **Every project has exactly one owner** — the person, or an organisation.
   What anyone else sees follows from that.
3. **Hours, not the person.** On its own projects an organisation sees start,
   end, duration, the entry's note, absences (date, type, half day), and the
   contract on the project — its terms and its balance (decision 32). Flow
   scores, apps, repos, idle time, biometrics, the
   coach and its memory, calendar, insights, tags and personal projects —
   including their existence — never cross. No setting changes this.
4. **Nothing is retroactive without consent.** Connecting a project the
   person already tracks shares history only from a day they choose.

And one that follows: **the person can always see what the organisation
sees**, on the "What Acme can see" page, which is the organisation's own read
narrowed to them — not a description of it.

---

## Decisions

The roadmap left three open and gated the stage on them. They were settled
first, then the model was built on them.

1. **The note crosses; tags do not.** Rule 3 names the entry's note, and the
   organisation reads it. The marker the epic asked for goes wherever a
   note is *shown* on an organisation's project — beside it, "Acme can read
   this note" (`TodayFeed`, `WeekDays`) — and, since #348, on the one input
   that writes one: the web app's session editor, where the marker describes
   the input itself and follows the project picked, so nobody writes
   something personal without seeing who reads it. (The companion's "How did
   it go?" sheet went with the last free-text inputs and has not returned;
   the API's wire rule — a string sets, an empty string clears, omitted
   keeps — means a client without the input cannot erase a note.) Any other
   surface that brings a note input back ships the marker the same way.
   Tags are derived from the daemon's flow windows — how someone worked, not
   what on — and stay on the far side with the flow scores. An absence's
   note never crosses either; an absence is its date, type and half day, as
   the timesheet already had it.
2. **No live presence, in this stage or any other.** The organisation's read
   takes finished entries only and carries no `running` flag, as 1c's report
   link does, so an employer cannot learn from its working-time record
   whether someone is at their desk now. The roadmap weighed "off by default,
   on with consent" and found it the one feature most likely to read as
   surveillance to the works councils this sells to. Not built, not planned.
3. **Erasure keeps the working-time record, and only that.** Deleting an
   account was total; now the rows an employer may be bound to keep survive:
   entries and absences stamped as an organisation's (start, end, project,
   note; date, type, half day), the balance adjustments and the contract
   behind a balance it read, and the name and address it knew the person by
   on their membership. Their `user_id` becomes a tombstone no account ever
   has, `erased:<membership id>`, one per organisation, so the record still
   groups one former member's rows and nothing in the system can be scoped to
   them. Tags, absence notes, the personal goal and local repo paths go with
   the account (`infrastructure/erasure.py`, `scripts/erase_account.py`).
   This is why "this row is an organisation's record" is a **property of the
   row** (`organisation_id` on the beat and the absence) and not a join
   through a project that is itself being deleted.

Then the model's own:

4. **Only `projects` gets a second owner.** `MongoStore._q` stamps `user_id`
   on every query of the repositories built on it (twenty-one now); stage 2
   widened exactly one. `MongoProjectRepository` reads a person's own
   documents plus the organisation projects they hold an active assignment
   to, and the others are untouched: a beat on an organisation's project is
   still the member's own document, user-scoped.
5. **An organisation's project document carries the organisation's fields and
   nothing personal.** `ORGANISATION_FIELDS` — name, description, colour,
   archived, kind, GitHub repo, category — live on the document, with
   `organisation_id` and no `user_id`. `PERSONAL_FIELDS` — the weekly goal
   and its overrides, the local repo paths that auto-start the timer, and
   the contract (which stage 3 let the employer write without moving it,
   decision 21) — live on the member's **assignment**, so two
   members of one project each keep their own, and so a document that
   reaches every paired device of every assigned member carries no one's
   repo paths. The repository merges the two on read into one `Project` and
   splits them on write; a member's write that changes an organisation field
   is a 409 `ORGANISATION_PROJECT` naming the field, and an admin writes
   those fields through the organisation's own routes.
6. **The contract lives on the member's assignment.** Stage 2 left the member
   its only writer, and stage 3 let the employer take the pen (decision 21).
   The grain was already per person, which is the grain a contract has, so
   stage 3 changed who may write and not where it lives.
   `docs/work-contracts.md` decision 1 — the day-job project *is* the contract
   — stands for a personal day job and is read through the assignment for an
   organisation's.
7. **The organisation's read is keyed on its own stamp.** A beat or absence
   written against an organisation's project is stamped `organisation_id` by
   the service that writes it (`TimerService.start_timer`,
   `BeatService.create_beat` / `update_beat`,
   `ContractService.record_absence`, and from stage 3 the employer's
   `EmploymentService.enter_time` and an approved absence request), and moving
   a beat to a personal project clears the stamp. `MongoOrganisationRecords`
   reads `{organisation_id, project_id ∈ its projects, end ≠ null}` — the one
   unscoped reader, in the shape of 1c's `MongoReportLinkLookup`. Beside the
   record it answers only two yes-or-no questions over the same stamp (whether
   a stamped timer still runs inside a month being approved, decision 23;
   whether a member has unshared rows on the project, decision 16) and reads
   the balance adjustments on an assigned member's project, which carry no
   stamp and make up the balance it is shown. A flow score, a tag, a biometric
   or another member's personal project is unreachable because the query for
   it is never made (`TestOrganisationWall`), not because a filter removed it.
   A beat on the organisation's project *without* the stamp — moved there by
   hand in the database, or before a connected project's `shared_from` — is
   not read.
8. **Connecting hands the document over and stamps the chosen history.** The
   personal fields move to a new assignment with `shared_from` = local
   midnight of the chosen day (or now, to start fresh); the document loses
   `user_id` and its personal fields and gains `organisation_id`, keeping its
   id, so every beat, absence and adjustment stays where it is (rule 1);
   then the member's own beats from that instant and absences from that day
   are stamped. A project billed to a client stays personal (409
   `PROJECT_HAS_BILLING`): billing is the person's, and an organisation's
   project is billed by nobody here (409 `ORGANISATION_PROJECT` on the
   billing route). Connecting creates a project the organisation did not
   make, named as it was; folding it into one the organisation already
   has is a second, deliberate act — the merge, decision 28 — never the
   connect's own.
9. **Leaving and removal end the assignments and move nothing.** The
   membership and every active assignment get an end instant; the project
   is then not found through the member's routes — which is how tracking
   stops, on every surface, with no new rule — and leaves their list. The
   stamped rows stay: the organisation keeps its record under `/record`, and
   the person keeps their own rows, read through their own user-scoped
   repository, as the read-only "Acme (left)" archive with a CSV. Rejoining
   reopens the membership; assignments are made again by an admin.
10. **Roles are owner, admin, member, each including the ones below.**
    Admins run members, invites, requests, projects, assignments, settings
    and read the record. (Stage 4 put manager and viewer between admin and
    member, with rights read off capabilities rather than the ladder, and
    shared the record with them: decision 25.) The owner role is given and
    taken by owners only, no invite carries it, and the last owner can
    neither leave, be removed
    nor be demoted (409 `LAST_OWNER`). A non-member and an unknown
    organisation read the same, 404 `ORGANISATION_NOT_FOUND`; a member
    without the role is 403 `ORGANISATION_ROLE_REQUIRED`.
11. **The API sends no email, and hands out no token.** An invitation to an
    address is a token the inviter passes on, and only the account holding
    that address can take it (anyone else gets 404). The invitee also finds
    at sign-in, under `/invitations`, *who* has invited them and as what —
    but not the token: an address is not verified at sign-up, so whoever
    registered it first must not be handed the way in. Joining takes both
    the link and the address. An invite link has no address, is reusable
    until it expires or is revoked, and with `requires_approval` makes a
    join request for an admin instead of a member. Every token is 32
    URL-safe bytes, stored as read, as 1c's are.
12. **The audit log is written from the start, before anything reads it.**
    `org_audit` records every membership, role, invite, request, project,
    assignment and connection event, and an account's erasure; the later
    stages add their own (contracts, absence requests, timesheets, entered
    time, teams, merges, closing, retention). Stage 4 reads it
    (`GET /{id}/audit`); it cannot be backfilled, so it was cheaper to have
    from stage 2.
13. **A backup carries the member's view and restores only their half.** The
    full export lists an organisation's project as the member sees it, with
    `organisation` set, and their entries on it with their stamps. On import,
    a project the account still holds through an assignment gets its
    personal fields back and its organisation fields left to the
    organisation (a rename since the backup is not undone); one it does not
    hold is left out with everything on it, reported under `skipped` as
    `ORGANISATION_PROJECT`. A backup never writes over an organisation's
    document.
14. **No device reaches `/api/organisations`.** A paired device tracks on an
    organisation's project through `/api/projects` like any other — the
    project document it is handed carries the organisation's name and logo,
    nothing private — and cannot invite, assign, read the record or connect a
    project. That is why connecting lives under the organisation's prefix
    and not under `/api/projects/{id}`, which devices match by prefix.
15. **The coach stays the member's.** It reads the member's merged projects
    (so it names their day job) and is given no organisation port: nothing in
    it reads another member.
16. **A balance is shown only when the record is whole.** A balance sums
    every hour since the contract began, so on a connected project with
    entries or absences before the day the member chose to share from it
    would carry what rule 4 keeps back. The record withholds it
    (`has_unshared`, a yes-or-no read that shows nothing) and shows it only
    when every entry and absence on the project is the organisation's —
    where it equals the member's own figure to the hundredth.
17. **Reassigning keeps the member's half; only a connect replaces it.** An
    ended assignment reopened by an admin keeps the goal, repo paths and
    contract it had, since the contract is behind a balance the
    organisation already read.
18. **The stamp on a restored beat is never the file's.** A beat the account
    already holds keeps the stamp it has; one new to the account takes the
    one the project as it stands gives — an organisation's, and started on
    or after the member's `shared_from`. A backup from before a connect
    cannot strip the record, and an edited one cannot plant it.
19. **The rows stay the person's to edit, until a month is approved.** A
    member can still delete or move an entry that is an organisation's
    record, before and after leaving: rule 1 says the data is theirs. Stage
    3's approved months are where an employer's guarantee begins: inside one,
    the write answers 409 `PERIOD_APPROVED` until the month is reopened
    (decision 23). The erasure pass keeps the record against the account
    going, not against the person's own edits.
20. **The last-owner check is made twice.** The count before a demotion,
    leave or removal is not atomic with the write, so after the write the
    count is read again and the write undone (409 `LAST_OWNER`) if it left
    no owner. Two owners leaving at once are both refused.

---

## Data model

New collections, none scoped by `user_id`:

- **`organisations`**: `name`, `logo_url`, `week_start` (`monday`,
  `saturday`, `sunday`), `holiday_country` / `holiday_subdivision` (checked
  against the calendar library at write time, as a contract's are),
  `timezone` (checked against the tz database), `retention_years` (decision
  30), `created_at`, `created_by`, and `closes_on` while it is closing
  (decision 29).
- **`org_members`**: one per person per organisation, reopened on rejoining
  — `organisation_id`, `user_id` (a tombstone after erasure), `role`,
  `name`, `email` (what the organisation knew them by, taken from the
  account on joining), `joined_at`, `left_at`, `left_reason` (`left`,
  `removed`, `erased`). Unique on `(organisation_id, user_id)`.
- **`org_invites`**: `organisation_id`, `token` (unique), `email` or null,
  `role`, `requires_approval`, `created_by`, `created_at`, `expires_at`
  (1–90 days), `accepted_at` / `accepted_by` (an addressed invite is taken
  once), `revoked_at`.
- **`org_join_requests`**: `organisation_id`, `user_id`, `invite_id`,
  `name`, `email`, `requested_at`, `decided_at`, `decision`, `decided_by`.
- **`org_assignments`**: one per member per project, reopened on
  reassigning — `organisation_id`, `project_id`, `user_id`, `shared_from`
  (an instant), `assigned_at`, `assigned_by`, `ended_at`, and the personal
  half of the project: `weekly_goal`, `goal_type`, `goal_overrides`,
  `autostart_repos`, `contract`, and `contract_managed` (decision 21).
  Unique on `(project_id, user_id)`.
- **`org_audit`**: `organisation_id`, `at`, `actor_user_id`, `event`,
  `subject_user_id`, `project_id`, `details`.
- **`org_teams`** (stage 4): `organisation_id`, `name`, `member_ids`,
  `created_at`.
- **`org_absence_requests`** (stage 3): `organisation_id`, `project_id`,
  `user_id`, `date`, `type`, `half_day`, `note` (to the decider), `status`,
  `requested_at`, `decided_at`, `decided_by`, `comment`.
- **`org_timesheets`** (stage 3): `organisation_id`, `project_id`,
  `user_id`, `month` (its 1st, in the organisation's timezone), `status`,
  `submitted_at`, `decided_at`, `decided_by`, `comment`, `frozen` (the
  `FrozenMonth`: `worked`, `expected`, `balance_end`, `entries`,
  `absence_days`) and `history` (each submit, decision and reopen: when, by
  whom, the comment). Unique on `(project_id, user_id, month)`.

Changed:

- **`projects`**: an organisation's document has `organisation_id` and no
  `user_id`, and only the organisation's fields. Indexed `(user_id,
  archived)` — added before any organisation code, since the read was about
  to become "mine, plus every organisation project I am assigned to" across
  every tenant, and measured in `TestProjectsIndex` — and `organisation_id`.
- **`timeLogs`** and **`absences`**: `organisation_id`, sparse, set when
  written against an organisation's project; indexed with `project_id` for
  the organisation's read. A beat a decider logged for the member also
  carries `entered_by` (decision 24).

The domain models are in `domain/models.py` under *Organisations*; the
rules in `domain/organisations.py` (`OrganisationService`) and, for stages
3–4, `domain/employment.py` (`EmploymentService`, which extends it and is
what every route is given); retention in `domain/retention.py` and
`infrastructure/retention.py`; the persistence in
`infrastructure/organisations.py` (`MongoOrganisationStore`,
`MongoOrganisationRecords`) and the approved-month lock in
`infrastructure/repositories.py` (`MongoPeriodLocks`); the ports in
`domain/ports.py`; the routes in `api/routers/organisations.py` and
`api/routers/employment.py`, both under `/api/organisations`.

---

## HTTP contract

Every route under `/api/organisations` is behind a session and refused to a
device token. "Admins" means owner or admin; "deciders" owners, admins and
managers for the members of their teams; "record readers" owners, admins
and viewers, and managers narrowed to their teams (decision 25).

| Route | Who | What |
|---|---|---|
| `GET /` | anyone | My memberships, ended ones included |
| `POST /` | anyone | Create; I am its owner |
| `GET /invitations` | anyone | Who has invited my account's email, and as what — no token |
| `GET /join`, `POST /join` (`X-Invite-Token`) | anyone | Preview, then join (`joined`) or request (`pending`). The token is in a header, not the path Cloud Run logs for 30 days |
| `GET /{id}`, `PUT /{id}` | members / admins | The organisation and my standing; its settings |
| `POST`, `DELETE /{id}/close` | owners | Start the notice period (or move its day); call it off (decision 29) |
| `DELETE /{id}` | owners | From the closing day on: hand members their projects back, then delete the organisation (decision 29) |
| `GET /{id}/members` | members | Active members, by the name and address they joined under |
| `PATCH /{id}/members/{uid}`, `DELETE …` | admins | Role; removal |
| `POST /{id}/leave` | members | Leave |
| `GET`, `POST /{id}/invites`, `DELETE /{id}/invites/{iid}` | admins | Open invites; a new one; revoke. The token is in these admins' answers and nowhere else |
| `GET /{id}/requests`, `POST /{id}/requests/{rid}` | admins | Waiting requests; approve or decline |
| `GET`, `POST /{id}/projects`, `PUT /{id}/projects/{pid}` | admins | The organisation's projects with who is on each (`?archived=`); create; the organisation's fields |
| `POST /{id}/projects/{pid}/merge` | admins | Fold `pid` into another of the organisation's projects (decision 28) |
| `PUT`, `DELETE /{id}/projects/{pid}/members/{uid}` | admins | Assign; unassign |
| `POST /{id}/connect` (`tz` required) | members | Connect one of my own projects from `share_from`, or null for now |
| `GET /{id}/record?month=&tz=` | record readers | What the organisation sees; a manager's narrowed to their teams |
| `GET /{id}/visible`, `/visible.csv` (`month=&tz=`) | members, former members | What it sees of me — the same read; the month as CSV |
| `GET /{id}/archive`, `/archive.csv` | members, former members | My own entries and absences that are its record |
| `GET`, `POST /{id}/teams`, `PUT`, `DELETE /{id}/teams/{tid}` | readers / admins | Teams: a manager's scope |
| `GET`, `PUT /{id}/projects/{pid}/members/{uid}/contract` | deciders | The contract on an assignment, managed or not (decision 32); `managed` takes or returns the pen |
| `POST /{id}/projects/{pid}/members/{uid}/adjustments` | deciders | A payout, reset or cap on a managed assignment |
| `POST /{id}/projects/{pid}/members/{uid}/entries` | deciders | Enter a finished session for a member, marked `entered_by` |
| `POST`, `GET /{id}/absence-requests` (`?pending=`), `POST …/{rid}/decision`, `DELETE /{rid}` | members / deciders | Ask; list (my own, or a decider's scope); decide (approve books the absence); withdraw |
| `POST`, `GET /{id}/timesheets` (`?month=`), `POST …/{tid}/decision`, `POST …/{tid}/reopen` | members / deciders | Submit a month; list (my own; a decider's scope; every sheet for a viewer); approve (freeze) or send back; reopen with a reason |
| `GET /{id}/audit?before=&limit=` | admins | The audit log, newest first (100 a page by default, at most 500) |
| `GET /{id}/record.csv`, `/compliance.csv` (`month=&tz=`) | record readers | The month flat, and per day with breaks and warnings |

The record's shape is written field by field (`RecordResponse`), as the
public report's is, so what crosses cannot grow by inheritance: the
`organisation` (`id`, `name`, `logo_url`), the `month` with its `first` and
`last` day, and per project (the organisation's own fields), per member,
`user_id`, `name`, `shared_from`, `active`, the month's `hours`, `entries`
(`id`, `day`, `start`, `end`, `hours`, `note`), `absences` (`date`, `type`,
`half_day`), `totals` (all-time entries and hours, first and last),
`has_contract` and `balance` (as of today, with its four terms). The
project and the totals are domain models embedded whole; neither carries
anything of the member's. Codes: `ORGANISATION_NOT_FOUND`
404, `ORGANISATION_ROLE_REQUIRED` 403, `ORGANISATION_PROJECT` 409,
`INVITE_NOT_FOUND` 404, `INVITE_EXPIRED` 410, `ALREADY_A_MEMBER` 409,
`JOIN_REQUEST_PENDING` 409, `JOIN_REQUEST_NOT_FOUND` 404, `MEMBER_NOT_FOUND`
404, `LAST_OWNER` 409, `OWNER_ROLE_RESERVED` 403, `NOT_ASSIGNED` 404,
`SHARE_FROM_IN_FUTURE` 409; stage 3 adds `CONTRACT_MANAGED` 409,
`NOT_MANAGED` 409, `PERIOD_APPROVED` 409, `MONTH_NOT_ENDED` 409,
`TIMESHEET_NOT_FOUND` 404, `TIMESHEET_APPROVED` 409,
`ABSENCE_REQUEST_NOT_FOUND` 404, `REQUEST_DECIDED` 409, `TEAM_NOT_FOUND`
404, `OUTSIDE_MANAGER_SCOPE` 403; the later stage-4 work adds
`MERGE_INTO_ITSELF` 409, `CLOSE_NOTICE_TOO_SHORT` 409,
`ORGANISATION_NOT_CLOSING` 409, `ORGANISATION_STILL_CLOSING` 409 and
`RETENTION_BELOW_FLOOR` 409. Shared codes answer here too:
`PROJECT_HAS_BILLING` 409 on connect, `UNKNOWN_HOLIDAY_REGION` 400 and
`INVALID_TIMEZONE` 400 on the settings and the employer's contract, and the
contract's own 409s (`ADJUSTMENT_OUTSIDE_BALANCE`,
`VACATION_OPENING_OUTSIDE_CONTRACT`) on the employer's writes.

On the member's own routes, a `Project` gains `organisation` (`id`, `name`,
`logo_url`, `shared_from`, `contract_managed`), a beat and an absence
`organisation_id`, a beat a decider logged `entered_by`, and
`PUT /api/projects/` answers 409 `ORGANISATION_PROJECT` for a change to an
organisation field, as do `/archive` and `/unarchive`. Starting a timer or
logging an entry on a project whose assignment has ended is a 404, as for a
project that does not exist.

---

## The UI's rules

- An organisation's project is **marked** where projects are listed, with
  `OrganisationMark`: the logo or a lettered tile, with the name on the
  projects index and the tile alone in the picker. The sidebar names the
  organisation on hover ("Project · Acme"), since a tile there cost the
  project's name its width. The companion puts the name under the kind
  ("Day job · Acme").
- The timeline offers **Everything · Personal · Acme** as pills over one
  feed (`?owner=`), never a workspace to switch into.
- On the project page the header carries the organisation (since when is
  in its tooltip, and in plain words in the rail's Organisation panel, with
  the timesheets to submit and the links to *What Acme can see* and to the
  organisation); the colour dot and the name are not controls; the settings
  drawer disables the organisation's fields and says whose they are, keeps
  the goal and repo paths editable, and the contract unless the organisation
  manages it, and replaces Archive with a line that leaving the
  organisation is how the project leaves the list. On a managed assignment,
  time off becomes **Ask for time off**, with the requests and Withdraw. A
  personal project of a member offers **Connect to an organisation…** (not
  on a billed or archived one): the organisation, and start fresh or share
  from a day.
- Wherever a note is shown on an organisation's project, and on the session
  editor's note input: "Acme can read this note". A session a decider
  logged is marked "entered for you" in the web app's timeline.
- `/organisations` lists the invitations waiting for me (who, and as what;
  joining takes the link I was sent, decision 11), my organisations with my
  role, and the ones I left ("Acme (left)" → the archive), and creates one.
  The sidebar's Organisations item counts the invitations waiting.
- `/organisations/:id` is the organisation, as tabs kept in `?tab=`, each
  role seeing only its own: admins *People* (members, teams, invites with
  the URL to copy, requests), *Projects* (assignments, a member's managed
  contract, entering time, Merge…), *Approvals*, *Timesheets*, *Audit* and
  *Settings* (with Closing for the owner); managers and viewers *Approvals*
  and *Timesheets*; members *Timesheets*. Everyone has *What Acme can see*
  in plain sentences with a link to the actual data (`/visible`), their own
  timesheets, their hours (the archive) and *Leave* (disabled, and saying
  why, for the last owner). Record readers have the month's record
  (`/record`, a manager's narrowed to their teams) with its two CSVs. A
  closing organisation says so on this page, to everyone.
- `/organisations/join/:token` is where an invite URL lands.

---

## Employment (stage 3) and scale (stage 4)

Stage 3 turns the contract into something two parties agree on; stage 4 adds
what only matters past a handful of people. Decisions 21–30:

21. **The contract stays on the assignment; management is a flag.** The
    employer takes an assignment's contract under its hand
    (`contract_managed`, written through `PUT …/members/{uid}/contract`),
    **starting from the terms the member recorded** — the answer to the
    contract-disagreement question the epic gated this stage on: the
    employer's terms arrive as an audited act, never as a silent recomputation
    of a balance the member relied on. While managed, the member's own
    contract, absence and adjustment writes answer 409 `CONTRACT_MANAGED`;
    their week, ledger, balance and vacation reads are untouched. Handing back
    (`managed: false`) returns the pen. Personal day jobs are exactly as they
    were — nothing forces anyone into an organisation
    (`docs/work-contracts.md` decision 1 stands, read through the assignment).
    In the SPA, the managed-contract dialog, while the contract is managed,
    lists the assignment's terms with the day each takes effect and which is
    in force, and edits, removes and adds them through the same term dialog
    the member's register uses, so one set of rules validates a term whoever
    writes it (#349). Editing is offered only where the organisation manages
    the contract: the API would take the write either way, but on an unmanaged
    assignment the terms are the member's, and writing them from the
    employer's side is the silent recomputation this decision refuses. Each
    write sends the whole contract beside `managed`, so
    `keep_unsent_contract_fields` holds the holiday lists and the entitlement
    that only the member's own form edits.
22. **An absence on a managed assignment is a request.** The member asks
    (`org_absence_requests` — date, type, half day, and a note *addressed to
    the decider*, which the record never shows); an owner, admin or scoped
    manager approves — which books the absence, stamped, through the
    member's own repository — or declines with a comment. A pending request
    can be withdrawn; a decided one is decided once (409
    `REQUEST_DECIDED`), atomically, so two deciders cannot both book it.
    Unmanaged assignments book directly, as before (409 `NOT_MANAGED` on a
    request there).
23. **Approval freezes, and a frozen month refuses edits.** A member submits
    a month once it has ended in the organisation's timezone
    (`org_timesheets`, one per project · member · month, with a history). A
    decider approves — storing `FrozenMonth`: worked, expected, entries,
    absence days and the balance at the close, **the first stored derived
    working-time figure** (the weekly digests store their own totals; no
    balance, ledger, billing or budget figure is stored) — or asks for
    changes with a comment. From approval on, every write dated inside the
    month answers 409 `PERIOD_APPROVED`: beat create, edit (either end of
    the move), delete, a back-dated timer start, absences, adjustments, and
    the employer's own entries alike (`MongoPeriodLocks`, checked in the
    member-side services, and the employer's own check in
    `EmploymentService`).
    Approval itself refuses while a stamped timer still runs inside the
    month — its hours are in no figure yet. Reopening needs a reason, is
    recorded in the sheet's history and the audit log, lifts the lock and
    drops the frozen figures; re-approval freezes afresh. Of the three
    options weighed (refused / flagged / amendment), this is "refused with a
    recorded way back", the only one a works council can sign.
24. **Admin-entered time is marked.** A decider logs a finished session for
    a member (`entered_by` on the beat): it lands on the member's own
    timeline marked "entered for you", is stamped as the organisation's,
    and is in the audit log — the notification the epic asked for is the
    member's own timeline showing it. Every surface shows the session; the
    web app's timeline (`TodayFeed`, `WeekDays`) is the one that marks it.
25. **Teams are a manager's scope.** A team (`org_teams`) is a name and its
    members. The **manager** role decides requests and timesheets, writes
    managed contracts and enters time for the members of the teams the manager
    is in — and for nobody else (403 `OUTSIDE_MANAGER_SCOPE`) — and reads the
    record narrowed to them. The **viewer** role (an accountant, a works
    council seat) reads the whole record, the CSVs and the teams, and changes
    nothing. Deciding and reading the record are properties on the role
    (`decides`, `reads_record`), not rungs of the ladder, so a manager does
    not read the whole record a viewer does; administering is the ladder
    from admin up.
26. **The compliance record is a read, not a store.** `GET
    /{id}/compliance.csv?month=` derives, per member, project and day:
    first start, last end, the breaks between entries, the total, and the
    warnings a working-time authority would raise — a day over 10 hours
    (§3 ArbZG, still current law; the June 2026 reform draft keeps the
    ceiling) and
    rest under 11 hours between working days (Directive 2003/88/EC art. 3).
    A warning is derived from the same rows on every read and never stored:
    an edit that repairs the day repairs the record. The law binds the
    employer per person, not per project — a day split over two projects is
    one working day, the night between two projects is one rest, and the
    whole-day figures ride in the warning's text so a per-project row still
    explains itself. Exactly at a threshold is lawful; the first day read
    raises no rest warning, since what came before the rows is not in them.
    `record.csv` is the same month as flat entry rows.
27. **Reminders are the surfaces, not emails.** The API sends no email
    (decision 11); what is missing or waiting shows where people already
    look — the member's timesheet list offers the ended months still to
    submit and marks the ones sent back, and the decider's Approvals tab
    counts and groups what waits. A digest or push is later work (#351).

28. **A merge moves rows, never stamps.** `POST /{id}/projects/{pid}/merge`
    (admins) folds one of the organisation's projects into another — the
    way out of the duplicate a connect leaves when the organisation
    already had a project for the same work. Every row keyed by the
    source (the members' own entries, absences and adjustments, and the
    absence requests) now keys by the target with its stamp untouched, so
    rule 4 holds without being re-decided: what the member chose to share
    stays shared from that instant, and what was private stays private,
    under the surviving project on their own timeline. Each active
    assignment folds into the target's, which survives as it stands
    (decision 17's spirit): the earlier `shared_from`, and the source's
    contract only where the target's assignment has none. Refused while
    an approved timesheet exists on either side (409 `PERIOD_APPROVED`
    naming the earliest frozen month): a stored close must not gain or
    lose rows silently — reopen first. A sheet submitted over the source
    alone is dropped and resubmitted over the merged project; the source
    document is deleted; the audit log holds the whole act, with counts.
    The repoint (`MongoOrganisationStore.repoint_project_rows`) is one of
    the four writes that cross user scopes, with erasure, an organisation's
    deletion (decision 29) and the retention purge (decision 30), and is
    made only after both projects are checked to be the same
    organisation's.

29. **Closing is notice; deletion is the connect run backwards.** An owner
    starts a clock (`POST /{id}/close`, at least 30 days out, 60 by
    default, judged in the organisation's timezone; posting again moves the
    day) that every member sees in-app, on the organisation's page — the
    notice decision 11's no-email rule leaves us. Tracking carries on
    until the day, and the closing can be called off (`DELETE
    /{id}/close`).
    `DELETE /{id}` works only from the day on (409
    `ORGANISATION_STILL_CLOSING` / `ORGANISATION_NOT_CLOSING`): each
    member is handed a personal copy of every project they hold rows or a
    contract on — the organisation's fields as they stood, their
    assignment's half, the contract theirs again whoever held the pen —
    their rows repointed to it and unstamped, archived where their
    assignment had ended. Then everything that was the organisation's
    goes, its working-time record included: the final `record.csv` and
    `compliance.csv` are the notice period's job and the copy that
    survives, said in the owner's UI in those words. Tombstoned rows go
    too — the record's keeper is destroying the record. Hand-backs run
    before the wipe, so a crash midway strands nothing of a member's.

30. **Retention has a statutory floor; expiry removes the record, not the
    person.** An organisation keeps its working-time record for
    `retention_years`, refused below the floor of its country (409
    `RETENTION_BELOW_FLOOR`: Spain's art. 34.9 ET gives 4, Germany 2,
    France, Austria and the Netherlands 1, Poland 10; a country the table
    does not know gets 4, so a gap can never permit deleting below a law we
    had not written down). The default is 4 years from the record's date —
    the strictest common floor, inside the CNIL's 5-year ceiling for
    time-clock data. The period applies to the organisation's record — the
    stamped entries and absences, the frozen months, the contract and
    adjustments behind a balance it read, and tombstoned ex-member rows —
    with the audit log living as long as the records it explains. Expiry
    removes the organisation's record, not the person's data: a living
    member's rows lose the stamp and are purely their own again; only
    tombstoned rows are deleted. The purge is an idempotent operator-run
    script in the shape of `scripts/erase_account.py`
    (`api/scripts/retention_purge.py`, dry by default), audited as
    `retention.purged` with counts, the cutoff and the years, and no data;
    nothing schedules it, so the beta auto-deletes nothing. DATA.md and
    PRIVACY.md changed in the same stage, since the setting is a promise
    they make.

### Settled after stage 4

Three questions the 2026-10-31 audit raised, answered the same day.

31. **An organisation left without an owner stays as it is.** Erasing the
    last owner's account is neither refused nor followed by a promotion: the
    membership ends like any other erasure, and the organisation runs on
    under its admins. Owner-only acts — granting the owner role, closing,
    deleting — wait until someone acts on it. Noticing an organisation with
    no owner is the operator's job, in a back office (#424), not something
    the product decides on the organisation's behalf. (The last-owner check of
    decisions 10 and 20 still guards leaving, removal and demotion: those
    are the organisation's own acts, an erasure is the person's.)
32. **Connecting shares the project, contract included — and sharing is not
    control.** A member who connects a project chooses to share what is on
    it with the organisation, the contract with the rest, and a contract on
    a project the organisation made is the terms its work is done under. So
    a decider (decision 25) reads the contract on any assignment it decides
    for, managed or not (`GET …/members/{uid}/contract`): its terms as well
    as the balance the record shows. Writing them stays the member's until
    the organisation manages the contract (decision 21). Sharing hands over
    no power to delete: an organisation removing a project from someone ends
    the assignment and nothing else, and an entry, absence or adjustment is
    deleted only by the person whose it is. The one exception is rows kept
    under a tombstone after an account's erasure (decision 3), which exist
    only as the organisation's record and go when it is deleted (decision
    29) or its retention expires (decision 30).
33. **A decider may approve their own timesheet and absence request, for
    now.** A manager's scope includes themselves, and owners and admins are
    unscoped; the approval is in the audit log like any other. Requiring a
    second person is a later decision, not an omission.

The audit log, written since stage 2, is now readable: `GET /{id}/audit`
(owners and admins), newest first, paged by instant.

### Stage 4 items that wait

Five, each an issue under
[#353](https://github.com/lanterno/beats/issues/353): money as a permission
of its own (#340), verified email domains (#341), SSO per organisation
(#342), SCIM (#343) and per-seat billing (#345). They are decisions rather
than omissions, and what each waits for — including the attestation shape
settled for #342 on 2026-10-28, and the pricing already decided for #345 — is
in [roadmaps/organisations.md](../roadmaps/organisations.md), with the rest of
what is not built. The sales and legal material of the epic's section 7
(#352) is drafted in [roadmaps/legal/](../roadmaps/legal/) and unreviewed by
counsel, and nothing there reaches a customer first.
