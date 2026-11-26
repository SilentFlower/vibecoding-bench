/** 随 CLI 读取标题响应观察 SSE 用量。@param {Response} response 模型原始响应。
 * @param {Function} report 用量回执。@return {Response} 交回原 CLI 的同一份流。
 */
export function observeTitle(response, report) {
  if (!response.ok || !response.headers.get('content-type')?.startsWith('text/event-stream')) {
    throw new Error('标题模型响应未返回 SSE');
  }
  const decoder = new TextDecoder();
  const usage = {};
  let pending = '';
  let stopped = false;
  const observer = new TransformStream({
    async transform(bytes, controller) {
      pending += decoder.decode(bytes, { stream: true });
      let newline;
      while ((newline = pending.indexOf('\n')) >= 0) {
        const line = pending.slice(0, newline);
        pending = pending.slice(newline + 1);
        if (!line.startsWith('data:')) continue;
        const event = JSON.parse(line.slice(5));
        if (event.type === 'message_start') {
          usage.message_id = event.message.id;
          usage.input_tokens = event.message.usage.input_tokens;
        } else if (event.type === 'message_delta' && event.usage) {
          usage.output_tokens = event.usage.output_tokens;
        } else if (event.type === 'message_stop') {
          if (stopped) throw new Error('标题流重复结束');
          stopped = true;
          await report(usage);
        }
      }
      // 与账号端 Messages 的 10 MiB 正文上限一致，防止无换行的异常流无限积压。
      if (pending.length > 10 * 1024 * 1024) throw new Error('标题 SSE 记录过长');
      controller.enqueue(bytes);
    },
    flush() {
      if (!stopped || pending.trim() || decoder.decode()) throw new Error('标题流未正常结束');
    },
  });
  return new Response(response.body.pipeThrough(observer), {status: response.status, headers: response.headers});
}
