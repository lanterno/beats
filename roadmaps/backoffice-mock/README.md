# The back office mock

The redesign of the operator's back office, as the owner reviewed it on
2026-11-08. [backoffice.md](../backoffice.md) is the plan that builds it, and its
§ *The design* says **what this mock gets wrong**. Read that list before building
from a picture: some controls here are postponed, and some promise what the
product cannot do.

Every figure, person and organisation in it is invented. Nothing here needs
Claude or anything installed.

- **`screens/`** shows what each screen looks like: one picture each, 1440 wide
  (the phone 390, the states sheet 1280).
- **`source/`** shows what each screen is made of: its markup, sample rows and
  behaviour, with the shared colours, type and spacing in `backoffice.css`.

Build in `backoffice/client`, with its own tokens and components. These files are
a reference: do not port the `.dc.html` format or import `backoffice.css`.

## Reading a source file

The files are written for a design tool, and they are meant to be read here, not
run. Each names a `./support.js`, which is that tool's renderer. It is Anthropic's
code and not this project's to publish, so it was deliberately not copied.

- The markup is inside `<x-dc>`. A `{{name}}` is filled from `renderVals()` in
  the `<script type="text/x-dc">` at the bottom of the file.
- That script also holds the sample rows and the behaviour. **What a picture cannot
  show is there:** a filter, a form's errors, what appears after "Do it".
- `<sc-for list="…" as="…">` repeats its contents, and `<sc-if value="…">` shows them
  on a condition.
- `<dc-import name="Sidebar">` places another file from this folder. `Sidebar` and
  `Topbar` are shared by the desktop screens.
- A `hint-…` attribute only tells the design tool how to lay out a preview.

## The screens

| Screen | Picture | Source |
|---|---|---|
| Today | [Main.png](screens/Main.png) | [Main.dc.html](source/Main.dc.html) |
| Work queue | [Queue.png](screens/Queue.png) | [Queue.dc.html](source/Queue.dc.html) |
| Find anything | [Palette.png](screens/Palette.png) | [Palette.dc.html](source/Palette.dc.html) |
| Runbooks | [Runbooks.png](screens/Runbooks.png) | [Runbooks.dc.html](source/Runbooks.dc.html) |
| Find an account | [Accounts.png](screens/Accounts.png) | [Accounts.dc.html](source/Accounts.dc.html) |
| One account | [Account.png](screens/Account.png) | [Account.dc.html](source/Account.dc.html) |
| Review before acting | [Review.png](screens/Review.png) | [Review.dc.html](source/Review.dc.html) |
| Trust and safety | [Trust.png](screens/Trust.png) | [Trust.dc.html](source/Trust.dc.html) |
| Organisations | [Orgs.png](screens/Orgs.png) | [Orgs.dc.html](source/Orgs.dc.html) |
| Organisation with no owner | [Org.png](screens/Org.png) | [Org.dc.html](source/Org.dc.html) |
| Incidents | [Incidents.png](screens/Incidents.png) | [Incidents.dc.html](source/Incidents.dc.html) |
| Incident room | [IncidentRoom.png](screens/IncidentRoom.png) | [IncidentRoom.dc.html](source/IncidentRoom.dc.html) |
| Releases | [Releases.png](screens/Releases.png) | [Releases.dc.html](source/Releases.dc.html) |
| Jobs and windows | [Jobs.png](screens/Jobs.png) | [Jobs.dc.html](source/Jobs.dc.html) |
| Capacity and cost | [Capacity.png](screens/Capacity.png) | [Capacity.dc.html](source/Capacity.dc.html) |
| Privacy and compliance | [Compliance.png](screens/Compliance.png) | [Compliance.dc.html](source/Compliance.dc.html) |
| Audit log | [Audit.png](screens/Audit.png) | [Audit.dc.html](source/Audit.dc.html) |
| Access and controls | [Access.png](screens/Access.png) | [Access.dc.html](source/Access.dc.html) |
| On call, phone | [Phone.png](screens/Phone.png) | [Phone.dc.html](source/Phone.dc.html) |
| Edge states | [States.png](screens/States.png) | [States.dc.html](source/States.dc.html) |
| Today at dusk | [Dusk.png](screens/Dusk.png) | [Dusk.dc.html](source/Dusk.dc.html) |

## Where this came from

Copied on 2026-11-09 from version `1794174489-564c` of
<https://claude.ai/artifact/SqiuodztBSFVZBrspexva2>, where it is interactive. That
page is private to the owner's Claude account. If the mock is revised there, copy
it here again so the two agree.

When a stage ships, delete the screens it built, as
[../README.md](../README.md) § *When something ships* says.
