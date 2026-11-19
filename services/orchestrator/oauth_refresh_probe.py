"""固定OAuth刷新探针，复用原脚本与Docker执行回执解析。"""
from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import nullcontext
from typing import ContextManager

from docker import APIClient


OAUTH_REFRESH_SCRIPT = r'''
set -eu
if [ -f /workspace/.claude.json ]; then
  cp /workspace/.claude.json "$HOME/.claude.json"
fi
DNS_READY_HOST="${DNS_READY_HOST:-example.com}"
for i in $(seq 1 45); do
  if grep -q '^nameserver 127[.]0[.]0[.]1' /etc/resolv.conf \
    && DNS_READY_HOST="$DNS_READY_HOST" node -e "require('dns').resolve4(process.env.DNS_READY_HOST || 'example.com', (err, addresses) => process.exit(!err && addresses && addresses.length ? 0 : 1))" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
node - <<'JS'
const fs = require('fs');
const os = require('os');
const path = require('path');

const TOKEN_URL = 'https://platform.claude.com/v1/oauth/token';
const CLIENT_ID = '9d1c250a-e61b-44d9-88ed-5944d1962f5e';
const credentialsPath = path.join(os.homedir(), '.claude', '.credentials.json');
const refreshBufferMs = Number(process.env.OAUTH_REFRESH_BUFFER_SEC || '600') * 1000;
const claudeCodeVersion = process.env.CLAUDE_CODE_VERSION || '2.1.293';
const boundedExecution = Boolean(process.env.V3_OAUTH_REFRESH_NOT_AFTER);
let submitted = false;

function emit(value) {
  process.stdout.write(`${JSON.stringify(boundedExecution ? {...value, submitted} : value)}\n`);
}

function normalizeScopes(value) {
  const items = Array.isArray(value)
    ? value
    : (typeof value === 'string' ? value.split(/\s+/) : []);
  const seen = new Set();
  const scopes = [];
  for (const item of items) {
    if (typeof item !== 'string') {
      continue;
    }
    const scope = item.trim();
    if (!scope || seen.has(scope)) {
      continue;
    }
    seen.add(scope);
    scopes.push(scope);
  }
  return scopes;
}

function oauthErrorCode(text) {
  try {
    const payload = JSON.parse(text);
    const code = payload && typeof payload.error === 'string'
      ? payload.error.trim()
      : '';
    return /^[A-Za-z0-9_.:-]{1,80}$/.test(code) ? code : '';
  } catch {
    return '';
  }
}

function oauthErrorSummary(status, text, retryAfter) {
  const parts = [`OAuth token 刷新失败: HTTP ${status}`];
  const code = oauthErrorCode(text);
  if (code) {
    parts.push(code);
  }
  if (Number.isFinite(retryAfter)) {
    parts.push(`retry_after_sec=${retryAfter}`);
  }
  return parts.join('; ');
}

async function main() {
  let data;
  try {
    data = JSON.parse(fs.readFileSync(credentialsPath, 'utf8'));
  } catch (error) {
    throw new Error(`.credentials.json 读取失败: ${error.message}`);
  }
  const oauth = data && data.claudeAiOauth;
  if (!oauth || typeof oauth !== 'object') {
    throw new Error('.credentials.json 缺少 claudeAiOauth');
  }
  if (
    process.env.OAUTH_FORCE_REFRESH !== '1' &&
    typeof oauth.accessToken === 'string' &&
    oauth.accessToken &&
    typeof oauth.expiresAt === 'number' &&
    oauth.expiresAt > Date.now() + refreshBufferMs
  ) {
    emit({skipped: true});
    return;
  }
  if (typeof oauth.refreshToken !== 'string' || !oauth.refreshToken) {
    throw new Error('OAuth refreshToken 为空，请重新登录账号');
  }
  const requestBody = {
    grant_type: 'refresh_token',
    refresh_token: oauth.refreshToken,
    client_id: CLIENT_ID,
  };
  const scopes = normalizeScopes(oauth.scopes);
  if (scopes.length) {
    // OAuth refresh 只能沿用现有授权，不能借刷新请求扩大 scope。
    requestBody.scope = scopes.join(' ');
  }
  if (boundedExecution && (!/^\d+$/.test(process.env.V3_OAUTH_REFRESH_NOT_AFTER) ||
      Date.now() >= Number(process.env.V3_OAUTH_REFRESH_NOT_AFTER) * 1000)) {
    emit({error: '原节点刷新启动许可已过期'});
    process.exit(1);
  }
  submitted = true;
  const response = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(requestBody),
  });
  const text = await response.text();
  if (!response.ok) {
    const retryAfter = Number.parseInt(response.headers.get('retry-after') || '', 10);
    emit({
      error: oauthErrorSummary(response.status, text, retryAfter),
      status: response.status,
      retry_after_sec: Number.isFinite(retryAfter) ? retryAfter : null,
      oauth_error: oauthErrorCode(text) || null,
    });
    process.exit(1);
  }
  let payload;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    throw new Error(`OAuth token 刷新响应不是 JSON: ${error.message}`);
  }
  if (typeof payload.access_token !== 'string' || !payload.access_token) {
    throw new Error('OAuth token 刷新响应缺少 access_token');
  }
  oauth.accessToken = payload.access_token;
  oauth.refreshToken = typeof payload.refresh_token === 'string' && payload.refresh_token
    ? payload.refresh_token
    : oauth.refreshToken;
  const responseScopes = normalizeScopes(payload.scope);
  if (responseScopes.length) {
    oauth.scopes = responseScopes;
  }
  const expiresIn = Number.isFinite(Number(payload.expires_in))
    ? Number(payload.expires_in)
    : 3600;
  oauth.expiresAt = Date.now() + Math.max(expiresIn, 60) * 1000;
  const tmp = `${credentialsPath}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
  fs.renameSync(tmp, credentialsPath);
  emit({refreshed: true, expiresAt: oauth.expiresAt});
}

main().catch((error) => {
  emit({error: error && error.message ? error.message : String(error)});
  process.exit(1);
});
JS
'''


def execute_oauth_refresh_probe(api: APIClient, actual_worker: str, command: list[str], environment: dict[str,str], *,
                                user: str, workdir: str, before_start: Callable[[str],None] | None = None,
                                launch_guard: Callable[[str],ContextManager] | None = None) -> dict:
    """执行原固定刷新探针，节点可在实际启动前持久登记并复核本次许可。

    :param api: 原Docker API客户端。
    :param actual_worker: 本次已核对的原账号容器。
    :param command: 调用方使用固定脚本构造的实际命令。
    :param environment: 原已冻结的执行环境。
    :param user: 原执行UID。
    :param workdir: 原固定HOME工作目录。
    :param before_start: 创建exec后、实际启动前的登记及许可回调。
    :param launch_guard: 节点登记与实际启动的短临界区；响应正文在锁外有界读取。
    :return: 原探针JSON结果或沿原合同的解析/退出错误。
    """
    execution=api.exec_create(actual_worker,command,stdout=True,stderr=True,user=user,
        environment=environment,workdir=workdir)
    with launch_guard(execution['Id']) if launch_guard is not None else nullcontext():
        if before_start is not None:
            before_start(execution['Id'])
        output=api.exec_start(execution['Id'],stream=True) if launch_guard is not None else api.exec_start(execution['Id'])
    if launch_guard is None:
        raw=output
    else:
        raw=bytearray()
        try:
            for chunk in output:
                raw.extend(chunk)
                if len(raw)>256*1024:
                    raise ValueError('节点固定刷新探针输出超过上限')
        finally:
            output.close()
    inspected=api.exec_inspect(execution['Id'])
    text=raw.decode('utf-8',errors='ignore').strip()
    try:
        parsed=json.loads(text)
    except json.JSONDecodeError:
        return {'error':'oauth refresh probe returned non-json output','raw':text}
    if inspected.get('ExitCode') not in (0,None) and not parsed.get('error'):
        parsed['error']=f"oauth refresh probe failed with exit {inspected.get('ExitCode')}"
    return parsed
