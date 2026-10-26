# Organisations

> LifePete is a personal tracker: one person, their projects, their time. An
> **organisation** is a party that owns projects and reads the hours on them
> — an employer, a team, a client big enough to want its own view. A person
> has **one account and one timeline**; joining an organisation adds its
> projects to that timeline, marked, and shows the organisation the hours on
> them and nothing else.

This is stage 2 of the organisations epic (#353): the foundations.
[organisations-roadmap.md](organisations-roadmap.md) holds the staging and
the reasoning that led here; this file records what was built and the
decisions it rests on, so later stages do not re-litigate them. Stage 1,
clients and billing, is in [billing.md](billing.md).

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
   end, duration, the entry's note, absences (date, type, half day), and a
   contract's balance. Flow scores, apps, repos, idle time, biometrics, the
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
   organisation reads it. Today no surface writes a note — the companion's
   "How did it go?" sheet went with the last free-text inputs, the web app
   takes none, and the API ignores a note on edit — so a note arrives only
   through an import, and the marker the roadmap asked for goes where a note
   is *shown* on an organisation's project: beside it, "Acme can read this
   note" (`TodayFeed`, `WeekDays`). Any surface that brings a note input back
   must ship the marker on the input with it. Tags are derived from the
   daemon's flow windows — how someone worked, not what on — and stay on the
   far side with the flow scores. An absence's note never crosses either; an
   absence is its date, type and half day, as the timesheet already had it.
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
   on every query of eighteen repositories; stage 2 widens exactly one.
   `MongoProjectRepository` reads a person's own documents plus the
   organisation projects they hold an active assignment to, and the other
   seventeen are untouched: a beat on an organisation's project is still the
   member's own document, user-scoped.
5. **An organisation's project document carries the organisation's fields and
   nothing personal.** `ORGANISATION_FIELDS` — name, description, colour,
   archived, kind, GitHub repo, category — live on the document, with
   `organisation_id` and no `user_id`. `PERSONAL_FIELDS` — the weekly goal
   and its overrides, the local repo paths that auto-start the timer, and
   (until stage 3) the contract — live on the member's **assignment**, so two
   members of one project each keep their own, and so a document that
   reaches every paired device of every assigned member carries no one's
   repo paths. The repository merges the two on read into one `Project` and
   splits them on write; a member's write that changes an organisation field
   is a 409 `ORGANISATION_PROJECT` naming the field, and an admin writes
   those fields through the organisation's own routes.
6. **The contract stays the member's in this stage**, on their assignment.
   Stage 3 makes the employer its writer; the grain is already per person,
   which is the grain a contract has, so stage 3 changes who may write and
   not where it lives. `docs/work-contracts.md` decision 1 — the day-job
   project *is* the contract — stands for a personal day job and is read
   through the assignment for an organisation's.
7. **The organisation's read is keyed on its own stamp.** A beat or absence
   written against an organisation's project is stamped `organisation_id` by
   the service that writes it (`TimerService.start_timer`,
   `BeatService.create_beat` / `update_beat`, `ContractService.record_absence`),
   and moving a beat to a personal project clears the stamp.
   `MongoOrganisationRecords` reads `{organisation_id, project_id ∈ its
   projects, end ≠ null}` and nothing else — the one unscoped reader, in the
   shape of 1c's `MongoReportLinkLookup`. A flow score, a tag, a biometric or
   another member's personal project is unreachable because the query for it
   is never made (`TestOrganisationWall`), not because a filter removed it. A
   beat on the organisation's project *without* the stamp — moved there by
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
   make, named as it was; stage 2 does not merge it into one the
   organisation already has.
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
    and read the record. The owner role is given and taken by owners only,
    no invite carries it, and the last owner can neither leave, be removed
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
12. **The audit log is written from the start and read by nothing.**
    `org_audit` records every membership, role, invite, request, project,
    assignment and connection event, and an account's erasure. Stage 4 reads
    it; it cannot be backfilled, so it is cheaper to have now.
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
19. **The rows stay the person's to edit, in this stage.** A member can
    still delete or move an entry that is an organisation's record, before
    and after leaving: rule 1 says the data is theirs, and nothing here is
    approved or closed yet. Stage 3's locked periods are where an employer's
    guarantee begins; the erasure pass keeps the record against the account
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
  `timezone` (checked against the tz database), `created_at`, `created_by`.
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
  `autostart_repos`, `contract`. Unique on `(project_id, user_id)`.
- **`org_audit`**: `organisation_id`, `at`, `actor_user_id`, `event`,
  `subject_user_id`, `project_id`, `details`.

Changed:

- **`projects`**: an organisation's document has `organisation_id` and no
  `user_id`, and only the organisation's fields. Indexed `(user_id,
  archived)` — the roadmap's fourth prerequisite, measured in
  `TestProjectsIndex` — and `organisation_id`.
- **`timeLogs`** and **`absences`**: `organisation_id`, sparse, set when
  written against an organisation's project; indexed with `project_id` for
  the organisation's read.

The domain models are in `domain/models.py` under *Organisations*; the
rules in `domain/organisations.py` (`OrganisationService`); the persistence
in `infrastructure/organisations.py` (`MongoOrganisationStore`,
`MongoOrganisationRecords`); the ports in `domain/ports.py`.

---

## HTTP contract

Every route under `/api/organisations` is behind a session and refused to a
device token. "Admins" means owner or admin.

| Route | Who | What |
|---|---|---|
| `GET /` | anyone | My memberships, ended ones included |
| `POST /` | anyone | Create; I am its owner |
| `GET /invitations` | anyone | Who has invited my account's email, and as what — no token |
| `GET /join/{token}`, `POST /join/{token}` | anyone | Preview, then join (`joined`) or request (`pending`) |
| `GET /{id}`, `PUT /{id}` | members / admins | The organisation and my standing; its settings |
| `GET /{id}/members` | members | Active members, by the name and address they joined under |
| `PATCH /{id}/members/{uid}`, `DELETE …` | admins | Role; removal |
| `POST /{id}/leave` | members | Leave |
| `GET`, `POST /{id}/invites`, `DELETE /{id}/invites/{iid}` | admins | Open invites; a new one (the token is in the answer, and nowhere else); revoke |
| `GET /{id}/requests`, `POST /{id}/requests/{rid}` | admins | Waiting requests; approve or decline |
| `GET`, `POST /{id}/projects`, `PUT /{id}/projects/{pid}` | admins | The organisation's projects with who is on each; create; the organisation's fields |
| `PUT`, `DELETE /{id}/projects/{pid}/members/{uid}` | admins | Assign; unassign |
| `POST /{id}/connect` (`tz` required) | members | Connect one of my own projects from `share_from`, or null for now |
| `GET /{id}/record?month=&tz=` | admins | What the organisation sees |
| `GET /{id}/visible?month=&tz=` | members, former members | What it sees of me — the same read |
| `GET /{id}/archive`, `/archive.csv` | members, former members | My own entries and absences that are its record |
| `GET`, `POST /{id}/teams`, `PUT`, `DELETE /{id}/teams/{tid}` | readers / admins | Teams: a manager's scope |
| `GET`, `PUT /{id}/projects/{pid}/members/{uid}/contract` | deciders | The employer's contract on an assignment; `managed` takes or returns the pen |
| `POST /{id}/projects/{pid}/members/{uid}/adjustments` | deciders | A payout, reset or cap on a managed assignment |
| `POST /{id}/projects/{pid}/members/{uid}/entries` | deciders | Enter a finished session for a member, marked `entered_by` |
| `POST`, `GET /{id}/absence-requests`, `POST …/{rid}/decision`, `DELETE /{rid}` | members / deciders | Ask, list, decide (approve books the absence), withdraw |
| `POST`, `GET /{id}/timesheets`, `POST …/{tid}/decision`, `POST …/{tid}/reopen` | members / deciders | Submit a month; approve (freeze) or send back; reopen with a reason |
| `GET /{id}/audit?before=&limit=` | admins | The audit log, newest first |
| `GET /{id}/record.csv`, `/compliance.csv?month=` | record readers | The month flat, and per day with breaks |

The record's shape is written field by field (`RecordResponse`), as the
public report's is, so what crosses cannot grow by inheritance: per project,
per member, `shared_from`, `active`, the month's `hours`, `entries` (`day`,
`start`, `end`, `hours`, `note`), `absences` (`date`, `type`, `half_day`),
`totals` (all-time entries and hours, first and last), `has_contract` and
`balance` (as of today, with its four terms). Codes: `ORGANISATION_NOT_FOUND`
404, `ORGANISATION_ROLE_REQUIRED` 403, `ORGANISATION_PROJECT` 409,
`INVITE_NOT_FOUND` 404, `INVITE_EXPIRED` 410, `ALREADY_A_MEMBER` 409,
`JOIN_REQUEST_PENDING` 409, `JOIN_REQUEST_NOT_FOUND` 404, `MEMBER_NOT_FOUND`
404, `LAST_OWNER` 409, `OWNER_ROLE_RESERVED` 403, `NOT_ASSIGNED` 404,
`SHARE_FROM_IN_FUTURE` 409; stage 3 adds `CONTRACT_MANAGED` 409,
`NOT_MANAGED` 409, `PERIOD_APPROVED` 409, `MONTH_NOT_ENDED` 409,
`TIMESHEET_NOT_FOUND` 404, `TIMESHEET_APPROVED` 409,
`ABSENCE_REQUEST_NOT_FOUND` 404, `REQUEST_DECIDED` 409, `TEAM_NOT_FOUND`
404, `OUTSIDE_MANAGER_SCOPE` 403.

On the member's own routes, a `Project` gains `organisation` (`id`, `name`,
`logo_url`, `shared_from`), a beat and an absence `organisation_id`, and
`PUT /api/projects/` answers 409 `ORGANISATION_PROJECT` for a change to an
organisation field, as do `/archive` and `/unarchive`. Starting a timer or
logging an entry on a project whose assignment has ended is a 404, as for a
project that does not exist.

---

## The UI's rules

- An organisation's project is **marked** wherever projects are listed —
  the index, the picker, the sidebar — with `OrganisationMark`: the logo, or
  a lettered tile, and the name. The companion puts the name under the kind
  ("Day job · Acme").
- The timeline offers **Everything · Personal · Acme** as pills over one
  feed (`?owner=`), never a workspace to switch into.
- On the project page the header carries the organisation and "shared
  since"; the colour dot and the name are not controls; the settings drawer
  disables the organisation's fields and says whose they are, keeps the
  goal, repo paths and contract editable, and replaces Archive with a line
  that leaving the organisation is how the project leaves the list. A
  personal project of a member offers **Connect to an organisation…**:
  the organisation, and start fresh or share from a day.
- Wherever a note is shown on an organisation's project: "Acme can read this
  note".
- `/organisations` lists invitations to accept, my organisations and the
  ones I left ("Acme (left)" → the archive). `/organisations/:id` is the
  organisation: for everyone, *What Acme can see* in plain sentences with a
  link to the actual data (`/visible`) and *Leave*; for admins, members,
  invites (with the URL to copy), requests, projects and assignments,
  settings, and the month's record (`/record`). `/organisations/join/:token`
  is where an invite URL lands.

---

## Employment (stage 3) and scale (stage 4)

Stage 3 turns the contract into something two parties agree on; stage 4 adds
what only matters past a handful of people. Decisions 21–27:

21. **The contract stays on the assignment; management is a flag.** The
    employer takes an assignment's contract under its hand
    (`contract_managed`, written through `PUT …/members/{uid}/contract`),
    **starting from the terms the member recorded** — the roadmap's
    "contract disagreement" answer: the employer's terms arrive as an
    audited act, never as a silent recomputation of a balance the member
    relied on. While managed, the member's own contract, absence and
    adjustment writes answer 409 `CONTRACT_MANAGED`; their week, ledger,
    balance and vacation reads are untouched. Handing back
    (`managed: false`) returns the pen. Personal day jobs are exactly as
    they were — nothing forces anyone into an organisation
    (`docs/work-contracts.md` decision 1 stands, read through the
    assignment).
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
    figure in the system** — or asks for changes with a comment. From
    approval on, every write dated inside the month answers 409
    `PERIOD_APPROVED`: beat create, edit (either end of the move), delete,
    a back-dated timer start, absences, adjustments, and the employer's own
    entries alike (`MongoPeriodLocks`, checked in the member-side services).
    Approval itself refuses while a stamped timer still runs inside the
    month — its hours are in no figure yet. Reopening needs a reason, is
    recorded in the sheet's history and the audit log, lifts the lock and
    drops the frozen figures; re-approval freezes afresh. Of the roadmap's
    three options (refused / flagged / amendment), this is "refused with a
    recorded way back", the only one a works council can sign.
24. **Admin-entered time is marked.** A decider logs a finished session for
    a member (`entered_by` on the beat): it lands on the member's own
    timeline marked "entered for you", is stamped as the organisation's,
    and is in the audit log — the "member notified" of the roadmap is the
    member's own timeline showing it, since every surface reads it.
25. **Teams are a manager's scope.** A team (`org_teams`) is a name and its
    members. The **manager** role decides requests and timesheets, writes
    managed contracts and enters time for the members of the teams the
    manager is in — and for nobody else (403 `OUTSIDE_MANAGER_SCOPE`) — and
    reads the record narrowed to them. The **viewer** role (an accountant,
    a works council seat) reads the whole record, the CSVs and the teams,
    and changes nothing. The capabilities are properties on the role
    (`administers`, `decides`, `reads_record`), not the ladder.
26. **The compliance record is a read, not a store.** `GET
    /{id}/compliance.csv?month=` derives, per member and day: first start,
    last end, the breaks between entries, and the total — the shape a
    working-time authority asks for. `record.csv` is the same month as flat
    entry rows. Rest-period and maximum-daily-hours warnings are later
    work, as the roadmap says.
27. **Reminders are the surfaces, not emails.** The API sends no email
    (decision 11); what is missing or waiting shows where people already
    look — the member's timesheet list says which months are unsubmitted or
    sent back, the decider's sections say what waits. A digest or push is
    later work.

The audit log, written since stage 2, is now readable: `GET /{id}/audit`
(owners and admins), newest first, paged by instant.

### Stage 4 items deliberately not built

Recorded here so they are decisions, not omissions:

- **Money as a permission**: there is still no organisation-side money —
  billing stayed personal (decision on `ORGANISATION_PROJECT` in billing) —
  so there is nothing for the permission to guard yet. When organisation
  money arrives, lean on the collection boundary as the roadmap says.
- **Verified email domains**: needs the email infrastructure the API
  deliberately does not have (decision 11). Without verification, a domain
  rule would hand memberships to whoever registers an address — the exact
  hole decision 11 closed for invitations.
- **SSO per organisation, and "required to enter"**: sessions deliberately
  do not record which door was used (PRIVACY.md: "nothing downstream knows
  which door"). Requiring SSO per organisation needs that recorded, which
  is a privacy decision to make on its own, not a feature to slip in.
- **SCIM** provisioning: its own protocol surface and credential story.
- **Retention settings**: nothing in LifePete auto-deletes (DATA.md); a
  stored setting nothing enforces would be a false promise. Decide the
  deletion machinery first.
- **Per-seat billing**: the first money flowing *to us* — a payment
  provider, tax, invoices, dunning — its own project, as the roadmap says.

## Left out, still

- **Merging** a connected project into one the organisation already has.
- **Deleting an organisation**; archiving its projects is the way out today.
- **A note input** on any surface, and with it the marker on the input.
- **Term editing in the employer's dialog**: the SPA's managed-contract
  dialog toggles management; the employer edits terms through the API until
  the contract form grows an employer mode.
