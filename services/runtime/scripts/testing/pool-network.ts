import { connect } from 'node:net';
import { mkdtemp, readFile, readlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { PrivateProcess } from './pool-process';
import { isObject } from '../../src/shared/errors';
import { LocalPoolStartupError, type LocalPoolStartupStage } from './local-pool-startup';

/** 代理只回传端口和计数，不通过本通道传递 TLS 或业务正文。 */
type ProxyFrame = { type: 'ready'; port: number } | { type: 'stats'; proxyRequests: number; rejectedRequests: number };

/** 校验隔离代理回执。 @param line 私有 JSONL 帧。 @return 已验证端口或计数。 */
function decodeProxyFrame(line: string): ProxyFrame {
  const value: unknown = JSON.parse(line);
  if (isObject(value)) {
    if (value.type === 'ready' && Number.isInteger(value.port) && Number(value.port) > 0 && Number(value.port) < 65536) return value as ProxyFrame;
    if (value.type === 'stats' && Number.isSafeInteger(value.proxyRequests) && Number(value.proxyRequests) >= 0 && Number.isSafeInteger(value.rejectedRequests) && Number(value.rejectedRequests) >= 0) return value as ProxyFrame;
  }
  throw new Error('代理私有回执错误');
}

/** 仅允许固定 CONNECT 进入宿主 Unix socket 的隔离代理。 */
export interface IsolatedProxy {
  url: string;
  namespace: string;
  interfaces: string[];
  readonly proxyRequests: number;
  readonly rejectedRequests: number;
  /** 关闭本次创建的连接和监听器。 @return 资源已释放。 */
  close(): Promise<void>;
}

/** 验证仅回环网络并实测非法目标拒绝，启动阶段不访问模型。
 * @param socketPath 宿主 TLS 接收端的私有 socket。
 * @return 已完成目标拒绝自检的代理。
 */
export async function startIsolatedProxy(socketPath: string): Promise<IsolatedProxy> {
  let root: string | undefined, stage: LocalPoolStartupStage = 'driver_isolation';
  let proxy: PrivateProcess<ProxyFrame> | undefined, closing = false, failure: unknown, loop = Promise.resolve();
  let proxyRequests = 0, rejectedRequests = 0;
  const close = async (): Promise<void> => { closing = true; try { await proxy?.close(); await loop; } finally { if (root) await rm(root, { recursive: true, force: true }); } };
  try {
    if (Bun.spawnSync(['ip','link','set','lo','up']).exitCode !== 0) throw new LocalPoolStartupError(stage, 'ISOLATION_CHECK_FAILED');
    const interfaces = (await readFile('/proc/net/dev', 'utf8')).split('\n').slice(2).filter(line => line.includes(':')).map(line => line.split(':')[0]!.trim());
    if (interfaces.length !== 1 || interfaces[0] !== 'lo' || Object.keys(process.env).some(name => /POOL|REQUESTER|PROXY|ANTHROPIC|CLAUDE/.test(name))) throw new LocalPoolStartupError(stage, 'ISOLATION_CHECK_FAILED');
    stage = 'workspace';
    root = await mkdtemp(join(tmpdir(), 'ccrb-proxy-'));
    stage = 'node';
    const node = Bun.which('node'); if (!node) throw new LocalPoolStartupError(stage, 'NODE_NOT_FOUND');
    stage = 'proxy_start';
    // 固定 Bun 管道在大正文回归中出现 TLS 解密失败，由隔离空间中的 Node 透明转发密文。
    let bundle: Awaited<ReturnType<typeof Bun.build>>;
    try { bundle = await Bun.build({ entrypoints: [resolve(import.meta.dir, 'pool-network-node.ts')], target: 'node', format: 'esm', outdir: root, naming: 'proxy.mjs' }); }
    catch { throw new LocalPoolStartupError('proxy_start', 'BUILD_FAILED'); }
    if (!bundle.success) throw new LocalPoolStartupError(stage, 'BUILD_FAILED');
    proxy = new PrivateProcess([node, join(root, 'proxy.mjs')], { HOME: root, LANG: 'C.UTF-8', PATH: process.env.PATH ?? '/usr/bin:/bin' }, decodeProxyFrame);
    await proxy.send({ socketPath });
    const ready = await proxy.next(5000); if (ready.type !== 'ready') throw new LocalPoolStartupError(stage, 'CHANNEL_INVALID');
    stage = 'proxy_probe';
    const deniedHttp = await fetch('http://127.0.0.1:' + ready.port + '/', { headers: { connection: 'close' } });
    await deniedHttp.arrayBuffer();
    const deniedConnect = await new Promise<boolean>((resolve, reject) => {
      const timer = setTimeout(() => { socket.destroy(); reject(new LocalPoolStartupError('proxy_probe', 'CHANNEL_TIMEOUT')); }, 3000);
      const socket = connect(ready.port, '127.0.0.1', () => socket.write('CONNECT forbidden.example:443 HTTP/1.1\r\nHost: forbidden.example:443\r\n\r\n'));
      socket.once('data', bytes => { clearTimeout(timer); socket.destroy(); resolve(bytes.toString().startsWith('HTTP/1.1 403')); });
      socket.once('error', error => { clearTimeout(timer); reject(error); });
    });
    for (let index = 0; index < 2; index++) { const frame = await proxy.next(3000); if (frame.type !== 'stats') throw new LocalPoolStartupError(stage, 'CHANNEL_INVALID'); proxyRequests = frame.proxyRequests; rejectedRequests = frame.rejectedRequests; }
    if (deniedHttp.status !== 403 || !deniedConnect || proxyRequests !== 1 || rejectedRequests !== 2) throw new LocalPoolStartupError(stage, 'TARGET_REJECTION_FAILED');
    const baseProxy = proxyRequests, baseRejected = rejectedRequests, channel = proxy;
    loop = (async () => { try { while (!closing) { const frame = await channel.next(0); if (frame.type !== 'stats') throw new Error('代理重复就绪'); proxyRequests = frame.proxyRequests; rejectedRequests = frame.rejectedRequests; } } catch (error) { if (!closing) failure = error; } })();
    return { url: 'http://127.0.0.1:' + ready.port, namespace: await readlink('/proc/self/ns/net'), interfaces,
      get proxyRequests() { if (failure) throw failure; return proxyRequests - baseProxy; }, get rejectedRequests() { if (failure) throw failure; return rejectedRequests - baseRejected; }, close };
  } catch (error) { const failure = new LocalPoolStartupError(stage, error); await close().catch(() => {}); throw failure; }
}
