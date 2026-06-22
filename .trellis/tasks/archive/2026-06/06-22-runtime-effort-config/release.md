# Release Operations

## Conclusion
Release operations exist.

## SQL Changes
None

## Configuration Changes
- Remote `.env` `VIBEBENCH_TAG` was updated to `a908b58`.
- `CLAUDE_CODE_EFFORT_LEVEL` remains the fallback value; WebUI runtime setting overrides it for new normal / batch runs.

## Batch / Deployment Scripts / Data Repair
- Built and pushed DockerHub images for `huajiwuyan/vibebench-orchestrator`, `huajiwuyan/vibebench-worker`, and `huajiwuyan/vibebench-sidecar` with tags `latest` and `a908b58`.
- Uploaded updated `docker-compose.remote.yml` and `webui/` files to `/root/vibecoding-bench`.
- Ran remote `docker compose -f docker-compose.remote.yml --env-file .env pull`.
- Pre-pulled `huajiwuyan/vibebench-worker:a908b58` and `huajiwuyan/vibebench-sidecar:a908b58`.
- Recreated remote orchestrator with `docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator`.

## External Systems / Dependent Platforms
- DockerHub image repository `huajiwuyan/vibebench-*`.
- Remote vibecoding-bench host from `.deploy/vibercoding-bench.env`.

## Release Order
1. Push code to `origin/main`.
2. Build and push DockerHub images with the same git SHA tag.
3. Upload remote bind-mounted files (`docker-compose.remote.yml`, `webui/`).
4. Update remote `.env` `VIBEBENCH_TAG`.
5. Pull images and force recreate orchestrator.
6. Verify WebUI and runtime settings API.

## Rollback Notes
Set remote `.env` `VIBEBENCH_TAG` back to the previous tag (`30f52db`) and run `docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator`. Restore the timestamped remote backups of `docker-compose.remote.yml` and `webui/` if frontend or compose rollback is needed.

## Post-release Verification
- Remote orchestrator image is `huajiwuyan/vibebench-orchestrator:a908b58`.
- Remote root page returns HTTP 200 and contains the new 思考预算 UI.
- Authenticated `GET /api/settings/runtime-effort` returns `configured_effort`, `env_default_effort`, `effective_effort`, and `allowed_efforts`.
