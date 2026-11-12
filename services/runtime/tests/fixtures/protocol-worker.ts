import { createInterface } from 'node:readline';
import { appendFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

/** 只用于协议故障注入的独立进程，不包含官方代码或模型访问。
 * @param scenario 需要注入的故障。
 * @return 控制管道关闭后退出。
 */
export async function fixtureWorker(scenario: string): Promise<void> {
  const id = process.env.CCRB_WORKER_ID!;
  const frame = (type: string, fields: Record<string, unknown> = {}): void => { process.stdout.write(JSON.stringify({ schema_version: 2, worker_id: id, type, ...fields }) + '\n'); };
  if (scenario === 'startup_exit') process.exit(17);
  if (scenario === 'startup_wait') await Bun.sleep(10000);
  if (scenario === 'startup_error' || scenario === 'startup_error_wrong_worker') {
    await new Promise<void>((resolve, reject) => process.stdout.write(JSON.stringify({ schema_version: 2, worker_id: scenario === 'startup_error' ? id : 'other-worker', type: 'worker_error', code: 'native_configuration', status: 503, error: '专用 CLI 配置已拒绝当前显式密钥' }) + '\n', error => error ? reject(error) : resolve()));
    process.exit(111);
  }
  frame('worker_ready', { version: '2.1.293', pid: process.pid,
    ...(scenario === 'cache_match' ? { cache_policy: 'sub2api' } : scenario === 'cache_mismatch' ? { cache_policy: 'preserve' } : {}),
    ...(scenario === 'telemetry_match' ? { telemetry: { policy: 'on', state: 'initialized' } } : scenario === 'telemetry_suppressed' ? { telemetry: { policy: 'on', state: 'suppressed' } } : scenario === 'telemetry_mismatch' ? { telemetry: { policy: 'off', state: 'off' } } : {}),
  });
  if (scenario === 'duplicate_ready') frame('worker_ready', { version: '2.1.293', pid: process.pid });
  if (scenario === 'startup_error_after_ready') frame('worker_error', { code: 'native_configuration', status: 503, error: '不应在握手后接纳' });
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  await new Promise<void>(resolve => {
    input.on('close', resolve);
    input.on('line', (line: string) => {
      const command = JSON.parse(line);
      if (command.type === 'worker_shutdown') { input.close(); return; }
      if (command.type !== 'request_start') return;
      appendFileSync('calls.txt', process.pid + ':' + command.request_id + '\n');
      const requestId = scenario === 'wrong_request' ? 'old-request' : command.request_id;
      const event = (payload: Record<string, unknown>): void => frame('request_event', { request_id: requestId, payload, ...(scenario === 'wrong_worker' ? { worker_id: 'old-worker' } : {}) });
      if (scenario === 'malformed') { process.stdout.write('{broken}\n'); return; }
      if (scenario === 'early_exit') process.exit(19);
      event({ type: 'cc_prepared', attempt: 1, headers: [], body: '{}', body_bytes: 2, body_sha256: createHash('sha256').update('{}').digest('hex') });
      event({ type: 'response_headers', attempt: 1, status: 200, headers: [] });
      event({ type: 'response_chunk', attempt: 1, data_b64: 'e30=' });
      if (scenario === 'stream_wait') return;
      event({ type: 'completed', attempt: 1, state: 'success' });
      if (scenario === 'double_terminal') event({ type: 'completed', attempt: 1, state: 'success' });
      if (scenario === 'missing_idle') return;
      frame('worker_idle', { request_id: requestId });
      if (scenario === 'late') setTimeout(() => event({ type: 'response_chunk', attempt: 1, data_b64: 'e30=' }), 20);
    });
  });
  process.exit(0);
}
