# Security

## Reporting a vulnerability

Report it privately through
[GitHub's advisory form](https://github.com/lanterno/beats/security/advisories/new), or
by email to ahmed.elghareeb@proton.me. Please don't open a public issue or Discussion.

Include what an attacker could do, and the steps or a proof of concept that shows it.
You'll get a reply once it has been read, the fix is made in a private fork, and you're
credited in the advisory unless you'd rather not be.

## Scope

- Everything in this repository: the API, the web app, the Mac and phone apps, `beatsd`,
  the VS Code extension and the wall clock firmware.
- The hosted service: **lifepete.com** and **api.lifepete.com**. Test it only against an
  account you created yourself; never access, change or delete another person's data, and
  don't run load or denial-of-service tests.

Out of scope: problems that need a compromised device or a malicious browser extension,
and reports from automated scanners without a demonstrated impact.

## Supported versions

lifepete.com runs `main`. For self-hosted deployments, fixes land on `main` and in the
next release; there are no backports to older ones.
