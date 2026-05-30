# Branch Protection Configuration for `main`

**Phase**: Phase 1 (Research Maturity)  
**Purpose**: Enforce code quality gate before merges to `main`  
**Status**: Ready to configure (requires GitHub web UI or organization admin)

---

## What to Configure

### Branch: `main`

Enable the following rules:

#### 1. **Require Pull Request Reviews Before Merging**
- ✅ Require at least **1 approval**
- ☐ Dismiss stale pull request approvals when new commits are pushed
- ☐ Require review from code owners (not needed yet — no CODEOWNERS file)

#### 2. **Require Status Checks to Pass Before Merging**
Status checks that must pass (select these):
- ✅ `test` (Python test suite via GitHub Actions)
- ✅ `lint` (ruff linting)
- ✅ `security` (bandit static analysis)

Treat skipped checks as failures: **No** (allow stale checks if re-run is expensive)

#### 3. **Require Branches to Be Up to Date Before Merging**
- ✅ Require branches to be up to date before merging (prevents merge conflicts)

#### 4. **Require Code Review from Code Owners**
- ☐ Skip (not configured yet; can add later with CODEOWNERS file)

#### 5. **Require Conversation Resolution Before Merging**
- ✅ Require all conversations on code to be resolved

#### 6. **Require Signed Commits**
- ☐ Skip for now (nice-to-have; can enable later)

---

## How to Set It Up (5 minutes)

### Via GitHub Web UI

1. Go to: **Settings → Branches**
2. Under "Branch protection rules," click **"Add rule"**
3. Branch name pattern: `main`
4. Check boxes as listed above
5. Click **"Create"**

### Verification

After setup, try to merge a PR without:
- An approval → **blocked** ✓
- Passing CI → **blocked** ✓
- Up-to-date branch → **blocked** ✓

---

## Why This Matters

| Benefit | Enables |
|---------|---------|
| No accidental merges to main | Confident patch releases (Phase 1.1) |
| CI must pass before merge | Establishes quality floor (534 passing tests must stay that way) |
| Code review required | Audit trail for institutional governance (Phase 1.5b) |
| Blocks merge until conversations resolved | Forces explicit decisions on feedback |

---

## Next Steps

1. **Configure** branch protection on `main` (GitHub web UI, 5 min)
2. **Test** by attempting a merge without review (should block)
3. **Document** (create `.github/BRANCH_PROTECTION.md` to codify the rule)
4. **Proceed** to Phase 1.1 (Conventional Commits & Auto-Changelog)

---

## Success Criteria

- [ ] Branch protection enabled on `main`
- [ ] At least 1 approval required
- [ ] Status checks enforced (test + lint + security)
- [ ] Stale branches cannot be merged
- [ ] Documentation committed

