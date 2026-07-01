# Release Operations

## Conclusion
Release operations exist.

## Evidence Checked
- task.json
- prd.md
- design.md
- implement.md / implement.jsonl / check.jsonl
- release.md was missing before finish-work
- git commits / changed files: `8ee5160`, `2ecf013`, `0c8d8f9`, `d149d49`

## Drift Check
Missing release.md. This file records the release operations that were already executed for this task.

## SQL Changes
- `cc2api` includes startup migrations/default changes for Claude Code `2.1.197`: settings default profile/range, account `canonical_env` values, and `allow_1m_models` default/migration from `opus` to `opus,claude-sonnet-5`.
- Deployment verification must include DB version distribution and settings checks on the target `cc2api` instance when releasing `cc2api` itself.

## Configuration Changes
- `vibecoding-bench` default Claude Code version changed to `2.1.197` in compose/env examples and orchestrator fallback paths.
- Remote `/root/vibecoding-bench/.env` was backed up and updated to:
  - `VIBEBENCH_TAG=0c8d8f9`
  - `CLAUDE_CODE_VERSION=2.1.197`

## Batch / Deployment Scripts / Data Repair
- Built and pushed DockerHub images:
  - `huajiwuyan/vibebench-orchestrator:latest` and `:0c8d8f9`
  - `huajiwuyan/vibebench-worker:latest` and `:0c8d8f9`
  - `huajiwuyan/vibebench-sidecar:latest` and `:0c8d8f9`
- Synced `docker-compose.remote.yml` to `/root/vibecoding-bench`.
- Ran remote pull and force recreate for orchestrator:
  - `docker compose -f docker-compose.remote.yml --env-file .env pull`
  - `docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator`
- Pre-pulled remote worker and sidecar images for tag `0c8d8f9`.

## External Systems / Dependent Platforms
- DockerHub repositories under `huajiwuyan/vibebench-*`.
- Remote vibecoding-bench host `23.80.83.23:/root/vibecoding-bench`.
- `cc2api` deployment remains a separate external release target if the upgraded `cc2api` service is not already deployed.

## Release Order
1. Push code commits for `cc2api` and parent `vibecoding-bench`.
2. Build and push DockerHub images with both `latest` and immutable SHA tag.
3. Update remote `.env` to the immutable tag and `CLAUDE_CODE_VERSION=2.1.197`.
4. Pull images and force recreate orchestrator.
5. Pre-pull worker and sidecar images for the same tag.
6. Verify HTTP, container env, logs, and relevant DB/settings state.

## Rollback Notes
- For vibecoding-bench remote deployment, set remote `VIBEBENCH_TAG` back to the previous tag, set `CLAUDE_CODE_VERSION` back to the previous deployed version if needed, then run `docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator`.
- For cc2api behavior, use the retained `2.1.195` built-in profile or roll back to the previous cc2api image/commit. If `allow_1m_models` needs to be tightened, update affected accounts back to `opus`.

## Post-release Verification
- Remote vibecoding-bench verification completed:
  - `http://23.80.83.23:8080/` returned `200`.
  - `/api/topics` returned `401` with auth enabled.
  - orchestrator container uses `huajiwuyan/vibebench-orchestrator:0c8d8f9`.
  - container env has `CLAUDE_CODE_VERSION=2.1.197`, worker image `huajiwuyan/vibebench-worker:0c8d8f9`, and sidecar image `huajiwuyan/vibebench-sidecar:0c8d8f9`.
- For cc2api deployment verification, confirm `curl /`, DB `canonical_env.version/version_base/build_time` distribution, settings allowed range/profile, and logs without error/panic/failure.
