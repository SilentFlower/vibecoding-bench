// 绑定文件由发送器在本次会话专属目录生成，服务端地址和授权均不取自 Messages。
import { endpoint, bearer } from './binding.js'

async function post($, action, value = {}) {
  const response = await $.http.fetch(endpoint + '/' + action, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + bearer },
    body: JSON.stringify(value),
  })
  if (!response.ok) throw new Error('发送器已结束本次会话')
  return JSON.parse(response.text)
}

/** 安装该进程的回合观察和外部工具回执钩子。@param on 官方事件注册器。@return 无。 */
export function register(on) {
  let pendingBlocks = null
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    await post($, 'ready')
    return result
  })
  on('prompt.submit', async ($, e, next) => {
    // 终端只输入发送器产生的固定标记。客户文本到达这里时已经越过终端命令解析。
    const { prompt, guard, blocks, media } = await post($, 'prompt', { marker: e.text })
    if (blocks) pendingBlocks = { marker: prompt, blocks, media }
    return next({ ...e, text: prompt, context: [...(e.context ?? []), guard] })
  }).catch(() => ({ drop: '交互请求归属已失效' }))

  on('session.append', { door: 'prompt' }, ($, e, next) => {
    if (!pendingBlocks || e.agentId) return next(e)
    const { content } = e.message
    const { marker, blocks, media } = pendingBlocks
    const index = content.findIndex(block => block.type === 'text' && block.text === marker)
    if (index < 0) return next(e)
    // 图像取自 CLI 实际粘贴的块。仅按公开输入顺序放回对应位置，仍由 CLI 保存和组装。
    pendingBlocks = null
    const images = media ? content.filter(block => block.type === 'image') : []
    let imageIndex = 0
    const submitted = blocks.map(block => media && block.type === 'image' ? images[imageIndex++] : block)
    if (imageIndex !== images.length || submitted.includes(undefined)) throw new Error('本轮图像未完整粘贴')
    const replaced = content.flatMap((block, slot) =>
      slot === index ? submitted : media && block.type === 'image' ? [] : [block])
    return next({ ...e, message: { ...e.message, content: replaced } })
  })

  on('turn.step', async function* ($, e, next) {
    if (e.agentId) throw new Error('当前会话不接受子代理回合')
    await post($, 'begin', { turn: e.turnId, step: e.index, model: e.model })
    const stream = next(e)
    // 内层一见完整工具块就会等待客户端回执。先公开原生增量并读到同一步的真实用量，
    // 再把这一工具之后的原始分片按原序交给内层，避免两个终端互等结束事件。
    let pending = null
    let pendingUnits = 0
    for (;;) {
      const item = await stream.next()
      if (item.done) {
        const response = item.value
        await post($, 'end', { turn: e.turnId, step: e.index, reason: response.stopReason,
          usage: response.usage, serverTools: response.serverToolUses?.length ?? 0 })
        if (pending) for (const part of pending) yield part
        return item.value
      }
      const chunk = item.value
      if (chunk.kind === 'tool' && !pending) pending = []
      if (pending) {
        // 预留正文的相同上限也约束完整工具等待，无法作为后续正文回传的调用不驻留。
        pendingUnits += JSON.stringify(chunk).length
        if (pendingUnits > 10 * 1024 * 1024) throw new Error('待交接的原生工具轮过大')
        pending.push(chunk)
      } else yield chunk
    }
  }).catch(async function* ($, e) {
    // 失败前如已提交，这里绝不再调用 next() 触发第二个模型请求。
    try { await post($, 'failed') } catch (_) {}
    return { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: null, usage: null }
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (!e.agentId) await post($, 'complete', { turn: e.turnId, aborted: e.isAborted })
    return result
  })

  // 内建工具在此直接拒绝。即使回执不可用也不进入服务器工具实现。
  on('tool.call', () => ({ deny: '工具由客户端执行' }))
    .catch(() => ({ deny: '工具由客户端执行' }))
  on('tool.check', () => ({ decision: 'deny', reason: '工具由客户端执行' }))
    .catch(() => ({ decision: 'deny' }))
  on('session.append', { door: 'tool-result' }, async ($, e, next) => {
    const ids = e.message.content.filter(b => b.type === 'tool_result').map(b => b.tool_use_id)
    let reply = await post($, 'results', { ids })
    while (reply.pending) {
      reply = await post($, 'results', { ids, ticket: reply.pending })
    }
    const { results } = reply
    const content = e.message.content.map(b => {
      if (b.type !== 'tool_result') return b
      const answer = results.find(r => r.tool_use_id === b.tool_use_id)
      if (!answer) throw new Error('客户端工具回执缺失')
      return { ...b, content: answer.content, is_error: answer.is_error === true }
    })
    return next({ ...e, message: { ...e.message, content } })
  })
}
