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
- `git` commits `b8d0ef3`, `b8766e9`, and `3143dfa`

## Drift Check

Missing `release.md`; release operations were reconstructed from the current task artifacts and committed implementation.

## SQL Changes

None.

## Configuration Changes

- [09-02-cc2api-cli-bg-status-classifier] Confirm the global setting `intercept_cli_bg_status_classifier_mode` exists after deployment and remains `passthrough` for production verification.
- [09-02-cc2api-cli-bg-status-classifier] Before the verification request, save and temporarily disable full 429/non-stream request-body logging, or set the body limit to `0`; restore the original values afterward.

## Batch / Deployment Scripts / Data Repair

- [09-02-cc2api-cli-bg-status-classifier] Wait for the `cc2api` image containing commit `b8d0ef3` to finish building.
- [09-02-cc2api-cli-bg-status-classifier] Check established connections before deployment and only pull and force-recreate during a low-connection window.
- [09-02-cc2api-cli-bg-status-classifier] Verify service health, deployed image identity, database setting, and recent error logs after deployment.

## External Systems / Dependent Platforms

- [09-02-cc2api-cli-bg-status-classifier] Use `https://us.flower-cli.com/v1/messages` for the production verification request.
- [09-02-cc2api-cli-bg-status-classifier] Select one active account with a non-empty `proxy_url`, create a one-time gateway token restricted to that account, keep the token only in a remote process variable, and delete it immediately after verification.

## Release Order

1. Confirm the image containing `b8d0ef3` is available.
2. Deploy during a low-connection window and verify service health and the default `passthrough` setting.
3. Save and restrict request-body logging for the verification window.
4. Create the account-restricted one-time token and send one synthetic Claude Code 2.1.257 `cli-bg` request through `us.flower-cli.com`.
5. Confirm the real upstream response is not 429 and the safe summary reports `shape_bypass=true` and `proxy_configured=true`.
6. Delete the token, restore logging, and confirm the production mode remains `passthrough`.

## Rollback Notes

- Restore the previous `cc2api` image if deployment health checks fail or normal `/v1/messages` traffic regresses.
- The additional setting key can remain in the database because older binaries ignore it.
- Do not use production `mock` mode as evidence that passthrough is fixed.

## Post-release Verification

- Verify the service is healthy and running the intended image.
- Verify the strong-shape synthetic request receives a real upstream non-429 response through an account with `proxy_url` configured.
- Verify logs contain only the safe bypass summary and do not contain the prompt, token, proxy URL, authorization data, cookies, or account identity mappings.
- Verify the one-time token is deleted, logging settings are restored, and `intercept_cli_bg_status_classifier_mode=passthrough` remains active.
