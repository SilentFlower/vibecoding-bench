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
- `cc2api` business commit `84b0016`
- Parent repository commit `c17660b`

## Drift Check

Missing `release.md`; release operations are derived from the completed task artifacts and Git
evidence.

## SQL Changes

- No manual SQL is required.
- Deploying the new `cc2api` build must run its existing startup migrations so historical default
  profile/range, account canonical environment, system-role allowlist, and bootstrap default values
  are conditionally upgraded while administrator custom values remain unchanged.

## Configuration Changes

- No new environment variable or secret is required.
- Do not manually add Fable 5.1 to `allow_1m_models`, disabled-thinking, or assistant-prefill lists.
- Preserve administrator-customized version ranges and model lists; only historical default values
  are eligible for automatic migration.

## Batch / Deployment Scripts / Data Repair

- Deploy the `cc2api` build containing commit `84b0016` and recreate/restart the service so startup
  migrations execute.
- Concrete host, image, compose, and health-check commands are owned by the existing
  `09-02-deploy-claude-code-2-1-257` task; this audit does not execute them.

## External Systems / Dependent Platforms

- No external platform configuration change is required by this task.
- Anthropic upstream may still return HTTP headers without a first SSE chunk; the implementation
  improves diagnosis but cannot eliminate that upstream condition.

## Release Order

1. Deploy and recreate/restart `cc2api` with commit `84b0016`.
2. Confirm startup migrations completed without overwriting customized settings.
3. Run the post-release verification below before treating the deployment task as complete.

## Rollback Notes

- Roll back to the previous `cc2api` image when the 2.1.257 profile causes a production regression.
- The 2.1.220 profile remains available for protocol rollback.
- Restore the pre-deployment database backup if settings or canonical environment migrations must
  be reversed. The appended Fable 5.1 system-role entry is not automatically removed by a code
  rollback.

## Post-release Verification

- Verify account `canonical_env.version`, `version_base`, `build_time`, and Node runtime reflect the
  2.1.257 default image where the historical default profile was in use.
- Verify customized allowed ranges and model lists remain unchanged, while the system-role list
  includes `claude-fable-5-1` without duplicate entries.
- Send representative Opus, Fable 5, Fable 5.1, and Haiku requests and confirm Fable 5.1 no longer
  fails local system-role validation.
- Verify a Fable 5.1 request does not gain `context-1m-2025-08-07` unless the existing account
  allowlist permits a client-supplied beta.
- Confirm zero-chunk timeouts log `upstream_first_byte_timeout`; confirm post-first-chunk silence
  logs `upstream_stream_idle_timeout` and that no keepalive is injected before the first real chunk.
- Treat CHK-001 as an accepted compatibility risk: Haiku historical prompt-marker and recursive
  schema matching remain intentionally broad until new capture evidence supports narrowing.
