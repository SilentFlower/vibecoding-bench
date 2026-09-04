# Release Operations

## Conclusion

Release operations exist.

## Evidence Checked

- `task.json`
- `prd.md`
- `design.md`
- `implement.md`
- `implement.jsonl`
- `check.jsonl`
- `c42d696 feat(protocol): 升级 cc2api Claude Code 2.1.260`
- `7aecda3 feat(protocol): 适配 Claude Code 2.1.260`

## Drift Check

Missing `release.md`; this file records the deployment boundary already defined by the task artifacts.

## SQL Changes

None. The release does not require manual SQL. The application performs conditional settings and
account canonical environment migration only for values that still match the 2.1.257 historical
defaults.

## Configuration Changes

- Deploying the new version changes the default profile to `2.1.260` and the default allowed range
  to `2.1.89-2.1.260`.
- Verify that administrator-customized allowed ranges, system-role settings, 1M allowlists, model
  policies, and account capability switches remain unchanged.

## Batch / Deployment Scripts / Data Repair

- Build and deploy the production `cc2api` image containing commit `7aecda3` through the dedicated
  deployment task `09-04-deploy-cc2api-claude-code-2-1-260`.
- Back up the production database and retain the previous production image before restarting the
  service with the new image.

## External Systems / Dependent Platforms

None beyond the existing production image registry and deployment environment.

## Release Order

1. Back up the production database and confirm the previous image remains available.
2. Build and publish the `cc2api` image from commit `7aecda3`.
3. Deploy the new image and allow the conditional default-value migration to run.
4. Complete the post-release verification before declaring the deployment complete.

## Rollback Notes

- Redeploy the previous production image and restore the database backup when the conditional
  migration must also be reverted.
- Append-only default list migration entries may remain after a code-only rollback, so verify the
  stored settings instead of assuming that rolling back the image removes them.
- The `2.1.257` profile remains available as the protocol-level rollback option.

## Post-release Verification

- Verify the default profile, allowed range, account canonical environment, User-Agent, build time,
  and telemetry identity resolve to `2.1.260`.
- Verify representative Opus, Sonnet, Fable 5.1, and Haiku requests against the captured protocol
  expectations.
- Verify the corrected `2.1.257` Fable 5 behavior and the explicit `2.1.257` rollback path.
- Verify customized settings and account capabilities were not overwritten by migration.
