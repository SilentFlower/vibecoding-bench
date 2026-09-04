# Release Operations

## Conclusion

Release operations exist and have been completed. The four child tasks delivered the cc2api
protocol profile, vibecoding-bench runtime update, production deployment, and `cli-bg` classifier
compatibility required for Claude Code 2.1.257.

## Evidence Checked

- `task.json`
- `prd.md`
- `design.md`
- `implement.md`
- `implement.jsonl`
- `check.jsonl`
- `research/*.md`
- Archived child task records and deployment evidence
- Git commits and production verification results

## Drift Check

`release.md` was missing. The parent task and all four completed child tasks consistently record
the 2.1.257 compatibility contract, release order, account-policy constraints, deployment
verification, and rollback requirements.

## SQL Changes

- cc2api migrated its default version profile, allowed version range, account canonical
  environment, system-role list, and bootstrap metadata to Claude Code 2.1.257.
- Migrations preserved administrator-defined settings and existing account `allow_1m_models`
  values.

## Configuration Changes

- cc2api's default protocol identity uses Claude Code 2.1.257 and its captured runtime metadata.
- vibecoding-bench's worker, orchestrator, Compose, WebUI, and example configuration default to
  Claude Code 2.1.257.
- `cli-bg` classifier handling defaults to real upstream pass-through; local simulation remains an
  explicit fallback mode.

## Batch / Deployment Scripts / Data Repair

- Production images were built by GitHub Actions and deployed from GHCR using immutable SHA tags
  and verified digests.
- Databases and deployment configuration were backed up and integrity-checked before recreation.
- Deployment occurred only after active connections, runs, workers, and sidecars reached the
  documented low-risk state.

## External Systems / Dependent Platforms

- Production target: `us.flower-cli.com`.
- GHCR supplied the cc2api gateway and the matching vibecoding-bench orchestrator, worker, and
  sidecar images.
- Anthropic upstream availability remains external; the project records and classifies zero-first-
  byte failures but does not fabricate SSE data.

## Release Order

1. Validate the protocol and runtime child tasks and publish immutable images.
2. Back up and upgrade cc2api, then verify the 2.1.257 profile, migrations, custom settings, and
   account policy preservation.
3. Deploy the matching vibecoding-bench images and verify the effective worker CLI version.
4. Deploy and verify the `cli-bg` compatibility change through the account proxy path.
5. Confirm HTTP health, database integrity, image identity, logs, and rollback evidence.

## Rollback Notes

Rollback must restore a mutually compatible vibecoding-bench and cc2api version pair. Prepare the
old vibecoding-bench state first, restore the cc2api database and image while bench remains stopped,
verify the old profile/range, and start the old orchestrator last. Exact backups, image IDs, hashes,
commands, and non-destructive validation results are retained in the archived
`09-02-deploy-claude-code-2-1-257` task.

## Post-release Verification

- Verify both service roots, container image IDs, and database integrity.
- Verify the cc2api 2.1.257 profile/range, model-specific CCH/beta behavior, Fable 5.1 system role,
  quota routing, and `cli-bg` pass-through behavior.
- Verify all vibecoding-bench worker creation paths use Claude Code 2.1.257 unless explicitly
  overridden.
- Verify account `allow_1m_models` values remain unchanged and no local version, migration,
  signature, or stream-classification regression appears in recent logs.
