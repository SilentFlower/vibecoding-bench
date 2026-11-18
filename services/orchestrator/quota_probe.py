"""本机与节点共用的原固定OAuth usage探针。"""
import json

QUOTA_PROBE_SCRIPT = r'''
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

const USAGE_URL = 'https://api.anthropic.com/api/oauth/usage';
const credentialsPath = path.join(os.homedir(), '.claude', '.credentials.json');
const claudeCodeVersion = process.env.CLAUDE_CODE_VERSION || '2.1.293';

function emit(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function loadCredentials() {
  if (!fs.existsSync(credentialsPath)) {
    throw new Error('.credentials.json 不存在，请先登录账号');
  }
  try {
    return JSON.parse(fs.readFileSync(credentialsPath, 'utf8'));
  } catch (error) {
    throw new Error(`.credentials.json 解析失败: ${error.message}`);
  }
}

function oauthSection(data) {
  const oauth = data && data.claudeAiOauth;
  if (!oauth || typeof oauth !== 'object') {
    throw new Error('.credentials.json 缺少 claudeAiOauth，无法查询 OAuth usage');
  }
  return oauth;
}

async function requestUsage(url, options) {
  let lastError = '';
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    try {
      if (process.env.V3_USAGE_NOT_AFTER) {
        const notAfter = Number(process.env.V3_USAGE_NOT_AFTER);
        if (!Number.isFinite(notAfter) || Date.now() >= notAfter * 1000) {
          return {error: '原usage执行许可已过期', submitted: false};
        }
      }
      const response = await fetch(url, {...options, signal: AbortSignal.timeout(15000)});
      const text = await response.text();
      if (!response.ok) {
        const retryAfter = Number.parseInt(response.headers.get('retry-after') || '', 10);
        return {
          error: `HTTP ${response.status}: ${text.slice(0, 1000)}`,
          status: response.status,
          retry_after_sec: Number.isFinite(retryAfter) ? retryAfter : null,
        };
      }
      let payload;
      try {
        payload = JSON.parse(text);
      } catch (error) {
        return {error: `usage parse failed: ${error.message}`, raw: text.slice(0, 1000)};
      }
      return payload;
    } catch (error) {
      lastError = error && error.message ? error.message : String(error);
      // 已经拿到 HTTP 响应时不能重试，尤其 429 会被一次点击放大成多次上游请求。
      if (process.env.V3_NATIVE_USAGE === '1' || attempt === 5) break;
      await sleep(attempt * 1000);
    }
  }
  return {error: lastError || 'request failed after retries'};
}

async function currentAccessToken(data) {
  const oauth = oauthSection(data);
  if (typeof oauth.accessToken !== 'string' || !oauth.accessToken) {
    throw new Error('OAuth accessToken 为空，等待后台刷新器刷新或重新登录账号');
  }
  return oauth.accessToken;
}

(async () => {
  try {
    let credentials = loadCredentials();
    let token = await currentAccessToken(credentials);
    const usage = await requestUsage(USAGE_URL, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'anthropic-beta': 'oauth-2025-04-20',
        'User-Agent': `claude-code/${claudeCodeVersion}`,
      },
    });
    emit(usage);
    if (usage && usage.error) {
      process.exit(1);
    }
  } catch (error) {
    emit({error: error && error.message ? error.message : String(error)});
    process.exit(1);
  }
})();
JS
'''


def node_usage_result(value: dict, credentials: dict) -> dict:
    """保留原usage字段并移除当前凭据及上游错误正文。

    :param value: 原固定探针的实际JSON结果。
    :param credentials: Node当前HOME，仅用于本地脱敏。
    :return: 有界额度结果；永久门禁只保留原结构化明确错误。
    """
    if value.get('error'):
        error=value['error']
        if isinstance(error,str) and error.startswith('HTTP '):
            try:
                parsed=json.loads(error.partition(': ')[2])
                error=parsed.get('error') if isinstance(parsed,dict) else None
            except ValueError:
                error=None
        code=(error.get('code') or error.get('type')) if isinstance(error,dict) else error
        result={'error':{'code':code} if code in ('account_on_hold','invalid_grant') else '所属节点额度查询失败'}
        if type(value.get('status')) is int and 100<=value['status']<=599:
            result['status']=value['status']
        if type(value.get('retry_after_sec')) is int and 0<value['retry_after_sec']<=8*86400:
            result['retry_after_sec']=value['retry_after_sec']
        return result
    oauth=credentials.get('claudeAiOauth',{})
    secrets=[oauth[key] for key in ('accessToken','refreshToken') if isinstance(oauth.get(key),str) and oauth[key]]
    def redact(item,depth=0):
        # 上游扩展字段继续保留；原HOME令牌和敏感键在进入回执前本地移除。
        if depth>32:
            raise ValueError('节点usage响应层级过深')
        if isinstance(item,str):
            for secret in secrets:
                item=item.replace(secret,'***')
            return item
        if isinstance(item,list):
            return [redact(child,depth+1) for child in item]
        if isinstance(item,dict):
            return {redact(key,depth+1):redact(child,depth+1) for key,child in item.items()
                if key.lower().replace('_','') not in ('accesstoken','refreshtoken','authorization','apikey')}
        return item
    result=redact(value)
    if len(json.dumps(result,allow_nan=False).encode())>16384:
        raise ValueError('节点usage响应超过原受控回执上限')
    return result
