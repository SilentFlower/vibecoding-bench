import { request } from 'node:https';
import { readFile } from 'node:fs/promises';
import { createInterface } from 'node:readline';

/** Node TLS 客户端只用于本机传输夹具，使用显式 CA 校验。 @return 一次请求的逻辑响应回执。 */
async function main(): Promise<void> {
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const first = await input[Symbol.asyncIterator]().next(); input.close();
  const setup = JSON.parse(first.value ?? 'null') as { socketPath: string; certFile: string; body: string; path: string; cancel: boolean; slow: boolean };
  const raw = Buffer.from(setup.body, 'base64'), ca = await readFile(setup.certFile);
  await new Promise<void>(resolve => {
    let sent = false;
    const done = (value: unknown): void => { if (!sent) { sent = true; process.stdout.write(JSON.stringify(value) + '\n', () => resolve()); } };
    const req = request({ socketPath: setup.socketPath, hostname: 'api.anthropic.com', ca, servername: 'api.anthropic.com', method: 'POST', path: setup.path, agent: false, headers: { Host: 'api.anthropic.com', 'content-type': 'application/json', 'content-length': String(raw.length), authorization: 'Bearer original-cc-canary', 'x-future-pool-test': 'preserved' } }, response => {
      const chunks: Buffer[] = []; let complete = false;
      response.on('data', (bytes: Buffer) => { chunks.push(bytes); if (setup.cancel) { response.destroy(); req.destroy(); } else if (setup.slow) { response.pause(); setTimeout(() => response.resume(), 2); } });
      response.on('end', () => { complete = true; });
      response.on('close', () => done({ status: response.statusCode, body: Buffer.concat(chunks).toString('base64'), closed: !complete }));
      response.on('error', () => {});
    });
    req.on('error', () => { if (!setup.cancel) done({ error: '本机 TLS 请求失败' }); }); req.end(raw);
  });
}

void main().then(() => process.exit(0)).catch(() => process.exit(1));
