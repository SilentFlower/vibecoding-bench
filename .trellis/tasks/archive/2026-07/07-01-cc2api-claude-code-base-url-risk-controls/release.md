# Release Operations

## Conclusion
Release operations exist.

## Evidence Checked
- task.json
- prd.md
- design.md
- implement.md / implement.jsonl / check.jsonl
- release.md: missing before finish-work
- git commits / changed files:
  - `27f00cd feat(claude-code): 增加 base URL 风险控制`
  - `00e63af chore(task): record cc2api base url risk controls`
  - `d319ccf chore(task): update cc2api-claude-code-base-url-risk-controls push snapshot`

## Drift Check
Missing release.md. Current release operations inferred from task requirements and changed files.

## SQL Changes
None. No schema migration is required.

## Configuration Changes
- New persisted setting key: `claude_code_context_sanitizer_mode`.
- Default value: `report_only`.
- Allowed values: `off`, `report_only`, `normalize`.
- Existing databases receive the default row through normal settings default insertion during startup/migration.

## Batch / Deployment Scripts / Data Repair
None. No one-off data repair or batch rerun is required.

## External Systems / Dependent Platforms
- Deploy `cc2api` service that consumes the `cc2api` submodule commit `27f00cd`.
- Parent repository `vibecoding-bench` pins the submodule through commit `00e63af`.

## Release Order
1. Confirm `cc2api` commit `27f00cd` is available on `origin/main`.
2. Update/deploy the parent repository commit that pins the new submodule.
3. Rebuild the `cc2api` frontend/backend artifact or Docker image, because `web/src/components/Settings.vue` changed.
4. Restart/recreate the `cc2api` service so the new binary and embedded frontend assets are active.

## Rollback Notes
- Roll back to the previous `cc2api` submodule commit if the gateway behavior regresses.
- As an operational mitigation, set `claude_code_context_sanitizer_mode=off` to disable currentDate scanning/normalization.
- `report_only` is the default and should not modify request bodies; `normalize` is opt-in.

## Post-release Verification
- Verify `/admin/settings` returns `claude_code_context_sanitizer_mode=report_only` by default.
- Save each allowed mode from the management page and confirm the gateway hot path reloads.
- In `report_only`, confirm currentDate findings produce only脱敏日志 and do not change the forwarded body.
- In `normalize`, confirm `Todayʹs date is YYYY/MM/DD.` normalizes to `Today's date is YYYY-MM-DD.` before CCH / `cc_version` refresh.
- Confirm telemetry sanitizer drops non-official base URL / gateway / proxy fields and keeps official Anthropic hosts.
