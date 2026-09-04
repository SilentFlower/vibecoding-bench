# Release Operations

## Conclusion

Release operations exist and have been completed. The production deployment originally used
cc2api `84b0016` and vibecoding-bench `e03b8e1`; production has since advanced to
vibecoding-bench `9a352db` while retaining Claude Code 2.1.257.

## Evidence Checked

- `task.json`
- `prd.md`
- `design.md`
- `implement.md`
- `implement.jsonl`
- `check.jsonl`
- `research/deploy-evidence.md`
- Git commits and changed files

## Drift Check

`release.md` was missing. The task artifacts and deployment evidence consistently record the
published image tags, database backups, production checks, rollback order, and verification
results.

## SQL Changes

- cc2api startup migration updated the Claude Code version profile, allowed range, account
  canonical environment, and system-role/bootstrap metadata to 2.1.257.
- The deployment preserved every account's existing `allow_1m_models` value.

## Configuration Changes

- vibecoding-bench set `CLAUDE_CODE_VERSION=2.1.257` and pinned all three images to one
  `VIBEBENCH_TAG`.
- The WebUI runtime version override remained 2.1.257.

## Batch / Deployment Scripts / Data Repair

- Both services were deployed from GitHub Actions/GHCR images identified by immutable SHA tags
  and digests.
- SQLite and deployment configuration backups were created and integrity-checked before
  containers were recreated.
- The gateway and orchestrator were recreated only after active connections and runs reached a
  low-risk window.

## External Systems / Dependent Platforms

- Production target: `us.flower-cli.com`.
- GHCR provided the cc2api, orchestrator, worker, and sidecar release images.

## Release Order

1. Verify and back up both services.
2. Deploy and verify cc2api 2.1.257 compatibility.
3. Deploy the matching vibecoding-bench orchestrator, worker, and sidecar images.
4. Verify HTTP health, database integrity, effective CLI version, account policy preservation,
   and recent logs.

## Rollback Notes

Rollback must restore the compatible vibecoding-bench 2.1.220 state before switching cc2api back
to its 2.1.220 database and image, then start the old orchestrator last. The exact non-destructive
commands, image IDs, backup paths, and integrity hashes are recorded in
`research/deploy-evidence.md`.

## Post-release Verification

- Both service roots return HTTP 200 and the target image IDs are running.
- cc2api reports the 2.1.257 profile/range and preserves custom system roles and 1M allowlists.
- A worker reports Claude Code 2.1.257, all three vibecoding-bench image tags match, and no active
  run or temporary worker/sidecar remains after verification.
- Recent logs contain no migration failure, local version rejection, signature failure, panic,
  or unexpected stream timeout.
