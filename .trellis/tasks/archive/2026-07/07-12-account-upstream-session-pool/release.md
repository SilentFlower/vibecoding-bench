# Release Operations

## Conclusion
Release operations exist.

## Evidence Checked
- task.json
- prd.md
- design.md / implement.md / implement.jsonl / check.jsonl
- release.md was missing before this finish-work run
- git commits / changed files:
  - cc2api `6c9b1cc feat(gateway): 支持账号级上游 session 池`
  - vibecoding-bench `ac2a163 chore(task): 记录账号级上游 session 池任务`

## Drift Check
Missing release.md. Current task evidence shows SQL migration and account-level configuration changes, so this release note was added during finish-work.

## SQL Changes
- `cc2api/src/store/db.rs` adds additive `accounts` columns for SQLite and PostgreSQL:
  - `upstream_session_pool_enabled`
  - `upstream_session_pool_size`
  - `upstream_session_ttl_minutes`
  - `upstream_session_refresh_policy`
- Startup migration uses idempotent `ALTER TABLE ... ADD COLUMN` statements. Existing accounts default to disabled upstream session pool.

## Configuration Changes
- New account-level settings are exposed through the management API and Accounts UI:
  - enable/disable upstream session pool
  - pool size
  - TTL minutes
  - refresh policy `mapped_request` / `owner_only`
- Defaults preserve old behavior: disabled by default; size `3`, TTL `60`, policy `mapped_request` are only effective after explicit enable.
- No new environment variables, secrets, external endpoints, or global feature flags were introduced.

## Batch / Deployment Scripts / Data Repair
None required beyond deploying the updated `cc2api` service so startup migration can run.

## External Systems / Dependent Platforms
None identified outside the `cc2api` gateway deployment.

## Release Order
1. Deploy updated `cc2api` binary and embedded web assets.
2. Let startup migration add the new account columns.
3. Verify existing accounts still have upstream session pool disabled.
4. Enable the pool manually per account when ready.

## Rollback Notes
- Immediate behavioral rollback: set `upstream_session_pool_enabled=false` or `upstream_session_pool_size=0` on affected accounts.
- Code rollback is safe because the database changes are additive; old code should ignore the extra columns.

## Post-release Verification
- Confirm the service starts successfully after migration.
- Confirm Accounts UI can read, edit, and save upstream session pool settings.
- Confirm existing accounts keep old behavior until explicitly enabled.
- For an enabled account, verify `/v1/messages` body/header use bounded upstream session ids while sticky/RPM logs still use real downstream sessions.
- Verify event_logging telemetry does not expose unmapped real sessions when pool mappings exist, and still fails open when mapping is unavailable.
