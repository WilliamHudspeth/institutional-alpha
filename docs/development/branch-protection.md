# Branch Protection

Rules for `main`, configured in GitHub under Settings, Branches, Add rule (pattern `main`).

| Rule | Setting |
|---|---|
| Require a pull request before merging | On, at least 1 approval |
| Dismiss stale approvals on new commits | Off |
| Require review from code owners | Off (no CODEOWNERS file) |
| Require status checks to pass | On: tests, lint, security |
| Require branches to be up to date | On |
| Require conversation resolution | On |
| Require signed commits | Off |

Reasons: no unreviewed changes reach `main`, CI must pass before merge, and review feedback is
resolved explicitly.

## Verify

Open a test PR and confirm that the merge button is blocked without an approval, without passing
checks, or on an out-of-date branch.

## Related

- [CI/CD](ci-cd.md): which workflows provide the status checks.
- [Releasing](releasing.md): how merged changes become releases.
- [Contributing](../../CONTRIBUTING.md): review standards.
