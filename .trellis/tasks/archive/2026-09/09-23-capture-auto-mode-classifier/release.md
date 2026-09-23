# Release Operations

## Conclusion

Release operations exist and have been completed. `vibecoding-bench` and `cc2api` were built,
deployed, and verified against the task acceptance criteria.

## Evidence Checked

- `task.json`, `prd.md`, `design.md`, `implement.md`, `capture-results.md`
- `implement.jsonl`, `check.jsonl`
- `vibecoding-bench` commits `9fb297f`, `b79319c`, `52be30d`
- `cc2api` commit `ded49ec`
- GitHub Actions runs `35813157934`, `35819194824`, `35819226483`
- Production container image, HTTP health, startup log summary, and SQLite version distribution

## Drift Check

Missing `release.md` before finish-work. This file records the deployment and verification already
completed for the task; it is consistent with `capture-results.md` and the pushed commits.

## SQL Changes

- `[09-23-capture-auto-mode-classifier]` The orchestrator startup migration adds the nullable
  `runs.capture_permission_mode` snapshot column and backfills the effective default through the
  application migration path. No manual SQL is required.
- `[09-23-capture-auto-mode-classifier]` `cc2api` has no schema change. Its existing startup
  migration kept all four accounts on the 2.1.280 canonical identity.

## Configuration Changes

- `[09-23-capture-auto-mode-classifier]` No new environment variable or secret is required.
- `[09-23-capture-auto-mode-classifier]` The production `cc2api` compose image pin now uses
  `sha256:acc469852e98466ecd779f3d538f55674f7d53b9c269a8e44bb279bd222b2276`.
- `[09-23-capture-auto-mode-classifier]` Existing account upstream proxies, OAuth profiles, and
  persistent permission defaults remain unchanged.

## Batch / Deployment Scripts / Data Repair

- `[09-23-capture-auto-mode-classifier]` `vibecoding-bench` was recreated from commit-tagged
  2.1.280 images before the formal capture matrix ran.
- `[09-23-capture-auto-mode-classifier]` `cc2api` was pulled and force-recreated only after the
  5674 established-connection count reached zero.
- `[09-23-capture-auto-mode-classifier]` No one-time data repair or background task replay is
  required.

## External Systems / Dependent Platforms

- `[09-23-capture-auto-mode-classifier]` GHCR contains the successful multi-architecture images
  produced by the recorded GitHub Actions runs.
- `[09-23-capture-auto-mode-classifier]` Formal protocol evidence remains on the bench server in
  the restricted `0700/0600` paths listed in `capture-results.md`.

## Release Order

1. Deploy the six-mode `vibecoding-bench` images.
2. Run the serial, rate-limited official capture matrix and finalize the protocol profile.
3. Build and deploy `cc2api@ded49ec` by immutable digest.
4. Verify HTTP health, container revision, logs, and account identity distribution.

This order has already been completed.

## Rollback Notes

- Restore the prior `cc2api` compose file from
  `/root/claude-code-gateway/backups/deploy-20260923T0444Z-safeguards-ded49ec/docker-compose.yml`,
  then run `docker compose --env-file ../.env up -d --force-recreate claude-code-gateway`.
- The previous `cc2api` image digest was
  `sha256:5471b9dd7baeba6f65e6a6794a2f7db20d36231aef4a646a2fa627b1ab9a7551`.
- Rolling back `vibecoding-bench` does not require deleting capture evidence or changing account
  credentials.

## Post-release Verification

- Container revision equals `ded49ecee38962972a56e4e77825b61b929dafb9`, restart count is zero,
  and both local and external HTTP checks return 200.
- Recent startup logs contain no panic, fatal, or error entries.
- All four accounts report `version=2.1.280`, `version_base=2.1.280`, and
  `build_time=2026-09-21T20:40:17Z`; the allowed range is `2.1.89-2.1.280`.
- The ten formal capture runs and their CCH, `cc_version`, beta, safeguards, and SSE results are
  recorded in `capture-results.md`.
