import { createServer } from 'node:http';
import { connect } from 'node:net';
import { createInterface } from 'node:readline';
import type { Duplex } from 'node:stream';

/** 在隔离空间以 Node 转发原始 TLS 字节，不解析业务或取得池凭据。 @return 关闭指令或父管道 EOF 后完成。 */
async function main(): Promise<void> {
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const iterator = input[Symbol.asyncIterator](), first = await iterator.next();
  const setup: unknown = JSON.parse(first.value ?? 'null');
  if (!setup || typeof setup !== 'object' || !('socketPath' in setup) || typeof setup.socketPath !== 'string') throw new Error('代理初始化错误');
  const socketPath = setup.socketPath;
  const sockets = new Set<Duplex>();
  let proxyRequests = 0, rejectedRequests = 0;
  const stats = (): void => { process.stdout.write(JSON.stringify({ type: 'stats', proxyRequests, rejectedRequests }) + '\n'); };
  const server = createServer((request, response) => { rejectedRequests++; stats(); request.resume(); response.writeHead(403); response.end(); });
  server.requestTimeout = 0;
  server.on('connect', (request, socket, head) => {
    proxyRequests++;
    if (request.url !== 'api.anthropic.com:443') { rejectedRequests++; stats(); socket.end('HTTP/1.1 403 Forbidden\r\n\r\n'); return; }
    stats();
    const target = connect({ path: socketPath }, () => {
      socket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
      if (head.length) target.write(head);
      socket.pipe(target); target.pipe(socket);
    });
    sockets.add(socket); sockets.add(target);
    socket.on('close', () => { sockets.delete(socket); target.destroy(); });
    target.on('close', () => { sockets.delete(target); socket.destroy(); });
    socket.on('error', () => target.destroy()); target.on('error', () => socket.destroy());
  });
  await new Promise<void>((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const address = server.address(); if (!address || typeof address === 'string') throw new Error('代理地址错误');
  process.stdout.write(JSON.stringify({ type: 'ready', port: address.port }) + '\n');
  try {
    while (true) {
      const next = await iterator.next(); if (next.done) break;
      const command: unknown = JSON.parse(next.value);
      if (!command || typeof command !== 'object' || !('type' in command) || command.type !== 'shutdown') throw new Error('代理指令错误');
      break;
    }
  } finally {
    input.close(); for (const socket of sockets) socket.destroy();
    await new Promise<void>(resolve => server.close(() => resolve()));
  }
}

void main().catch(() => { process.stderr.write('隔离代理已关闭\n'); process.exit(1); });
