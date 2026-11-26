/** 在隔离镜像内把获准的模型正文交给本轮原生网络会话。 */
import { endpoint, bearer } from './binding.js';

const NativeSession = Bun.FetchSession;
const control = new URL(endpoint);
if (control.protocol !== 'http:' || control.hostname !== '127.0.0.1' || !control.port) {
  throw new Error('测试回调必须属于本机独立会话');
}

/** 逐块等待账号端接收，保留原响应的读取速度。
 * @param {string} id 本次认领编号。@param {string} action 回报类型。
 * @param {Uint8Array} bytes 本次新增字节。@return {Promise<void>} 账号端接收确认。
 */
async function report(id, action, bytes) {
  const response = await fetch(new URL('/native-lab/' + id + '/' + action, control), {
    method: 'POST', headers: { authorization: 'Bearer ' + bearer }, body: bytes, redirect: 'error',
  });
  if (response.status !== 204) throw new Error('本次模型事件未被接收');
}

Bun.FetchSession = class extends NativeSession {
  /** 使用本轮原生网络方法发送模型请求，让两个消费者共享一次读取。
   * @param {string|URL} target 原目标。@param {RequestInit} init 原生调用选项。
   * @return {Promise<Response>} 交给交互 CLI 的响应。
   */
  async fetch(target, init) {
    const ready = await super.fetch(target, init);
    if (ready.headers.get('content-type') !== 'application/vnd.flower.native-lab+json') return ready;
    const source = new URL(target);
    if (source.origin !== control.origin || !/^\/model\/[^/]+\/v1\/messages$/.test(source.pathname)) {
      throw new Error('原生测试提交来自其他入口');
    }
    const grant = await ready.json();
    if (grant.kind === 'session_title') {
      const response = await super.fetch('https://model-probe.invalid/v1/messages', {
        ...init, proxy: grant.proxy, redirect: 'error',
      });
      const { observeTitle } = await import('./title-usage.mjs');
      return observeTitle(response, async usage => {
        const receipt = await fetch(new URL('/native-title/' + grant.id, control), {
          method: 'POST', headers: {authorization: 'Bearer ' + bearer},
          body: JSON.stringify(usage), redirect: 'error',
        });
        if (receipt.status !== 204) throw new Error('标题用量回执未被接受');
      });
    }
    if (grant.probeProxy) {
      // 两种常规代理配置均在同一进程内测试，只访问验收器的保留域名，沿用原会话网络隔离。
      const results = {};
      for (const [name, proxy] of Object.entries({session: control.origin, account: grant.probeProxy})) {
        try {
          const check = await super.fetch('https://model-probe.invalid/v1/messages', {
            method: 'POST', headers: {'content-type': 'application/json'}, body: grant.body,
            redirect: 'error', proxy, signal: AbortSignal.timeout(5000),
          });
          results[name] = String(check.status);
          await check.body?.cancel();
        } catch (error) {
          results[name] = String(error.code || error.name);
        }
      }
      await report(grant.id, 'proxy-check', new TextEncoder().encode(JSON.stringify(results)));
    }
    // 在模型接收前重放一次种子调用，证明同一步在账号端只能被认领一次。
    const repeatHeaders = new Headers(init.headers);
    repeatHeaders.set('x-native-lab-repeat', '1');
    const repeat = await super.fetch(target, { ...init, headers: repeatHeaders });
    await repeat.body?.cancel();
    if (repeat.status !== 409) throw new Error('重复的模型步骤未被拒绝');
    const headers = new Headers(init.headers);
    for (const [name, value] of Object.entries(grant.headers)) headers.set(name, value);
    const model = new URL('/native-lab/' + grant.id + '/v1/messages', control);
    model.protocol = 'https:';
    const targetUrl = grant.kind === 'main' ? 'https://model-probe.invalid/v1/messages' : model.href;
    const response = await super.fetch(targetUrl, {
      ...init, headers, body: grant.body, redirect: 'error', ...(grant.proxy ? {proxy: grant.proxy} : {}),
    });
    if (!response.ok || response.headers.get('content-type') !== 'text/event-stream') {
      await report(grant.id, 'abort', new Uint8Array());
      return response;
    }
    const reader = response.body.getReader();
    const stream = new ReadableStream({
      async pull(controller) {
        try {
          const { done, value } = await reader.read();
          if (done) {
            await report(grant.id, 'end', new Uint8Array());
            controller.close();
          } else {
            await report(grant.id, 'bytes', value);
            controller.enqueue(value);
          }
        } catch (error) {
          await reader.cancel().catch(() => {});
          await report(grant.id, 'abort', new Uint8Array()).catch(() => {});
          controller.error(error);
        }
      },
      async cancel(reason) {
        await reader.cancel(reason);
        await report(grant.id, 'abort', new Uint8Array()).catch(() => {});
      },
    });
    return new Response(stream, { status: response.status, headers: response.headers });
  }
};
