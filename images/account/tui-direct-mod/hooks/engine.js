const modelURLs = new Set([
  'https://api.anthropic.com/v1/messages',
  'https://api.anthropic.com/v1/messages?beta=true',
])

async function post($, binding, action, payload) {
  const response = await $.http.fetch(binding.endpoint + '/direct/' + action, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + binding.bearer },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('当前模型步骤的直发许可已失效')
  return JSON.parse(response.text)
}

/** 在正式托管策略中注册模型引擎的单次许可。@param on 官方 Mod 注册器。@return 无。 */
export function register(on) {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    const path = await $.env.get('FLOWER_TUI_DIRECT_BINDING')
    if (typeof path === 'string') await post($, JSON.parse(await $.fs.read(path)), 'ready', {})
    return result
  })
  on('http.fetch', async ($, e, next) => {
    const address = String(e.url ?? e.init?.url)
    if (!/^https?:\/\/(?:[^/?#]*@)?api\.anthropic\.com\.?(?::\d+)?(?:[/?#]|$)/i.test(address)) return next(e)
    const origin = next.origin
    if (origin?.plugin !== 'engine' || origin.tier !== 'core' || !modelURLs.has(address)
        || e.init?.method !== 'POST' || typeof e.init.body !== 'string') {
      return { deny: '当前会话仅允许通过已认领的 Messages 请求访问模型' }
    }
    const path = await $.env.get('FLOWER_TUI_DIRECT_BINDING')
    if (typeof path !== 'string') return { deny: '当前账号缺少直发绑定' }
    const binding = JSON.parse(await $.fs.read(path))
    const { ticket } = await post($, binding, 'permit', { url: address, body: e.init.body })
    if (typeof ticket !== 'string') return { deny: '当前模型请求缺少发送许可' }
    // 内层继续持有原 HTTPS 连接。响应状态通过一次性票据回到同一个 sender 预留。
    const reply = await next(e)
    const value = reply?.value
    const headers = value?.headers
    const requestId = Array.isArray(headers)
      ? headers.find(pair => pair[0].toLowerCase() === 'request-id')?.[1]
      : headers?.['request-id']
    await post($, binding, 'response', { ticket, status: value?.status ?? null,
      streaming: value?.isStreaming === true, requestId })
    return reply
  }).catch(() => ({ deny: '当前模型请求的受管直发校验失败' }))
}
