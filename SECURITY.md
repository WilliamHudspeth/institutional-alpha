# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.4.x (release candidate) | Yes |
| Earlier | No |

## Reporting a vulnerability

Do not open a public issue for a security problem.

Report it privately through the repository's Security tab ("Report a vulnerability"), or contact
the maintainer through the address on the GitHub profile. Include the affected version, steps to
reproduce, and the impact you see.

This is a single-maintainer project, so response times are best effort. If a report is accepted, a fix is released out of band (see
[releasing](docs/development/releasing.md)) and credited in the release notes unless you ask
otherwise. If it is declined, you will get the reason.

## Scope

- Credentials are stored outside the repository, in `~/.institutional-alpha/credentials.json`
  with owner-only permissions. Do not commit keys.
- Dependencies are scanned in CI with bandit, pip-audit, safety and CodeQL.
- Issues that make a valuation output silently wrong (for example a fabricated default) are
  treated as integrity bugs and are in scope.
