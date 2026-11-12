import { describe, expect, test } from 'bun:test';
import { BridgeError } from '../../src/shared/errors';
import { decodeLocalPoolStartup, LocalPoolStartupError } from '../../scripts/testing/local-pool-startup';
import { decodeForwarderFrame } from '../../scripts/testing/pool-common';
import { decodeLocalDriverFrame } from '../../scripts/testing/local-pool-protocol';
import { PrivateProcess, PrivateProcessError } from '../../scripts/testing/pool-process';

const secret = 'startup-private-canary-62935';

describe('本地池启动诊断', () => {
  test('只接纳阶段和直接白名单代码，未知及嵌套原因不猜测', () => {
    expect(decodeLocalPoolStartup({ stage: 'tls_probe', failureCode: 'CERT_NOT_YET_VALID', raw: secret })).toEqual({ stage: 'tls_probe', failureCode: 'CERT_NOT_YET_VALID' });
    for (const value of [null, [], secret, {}, { stage: secret, failureCode: secret }]) expect(decodeLocalPoolStartup(value)).toEqual({ stage: 'unknown', failureCode: 'UNKNOWN' });
    const error = new LocalPoolStartupError('tls_probe', { code: 'ECONNRESET', message: secret, cause: { code: secret } });
    expect(error).toBeInstanceOf(BridgeError); expect(error.code).toBe('local_pool_startup'); expect(error.status).toBe(503);
    expect(error.startup).toEqual({ stage: 'tls_probe', failureCode: 'ECONNRESET' });
    expect(error.message).not.toContain(secret); expect(JSON.stringify(error)).not.toContain(secret); expect(error.cause).toBeUndefined();
    expect(new LocalPoolStartupError('forwarder_start', { cause: { code: 'EACCES' }, message: secret }).startup).toEqual({ stage: 'forwarder_start', failureCode: 'UNKNOWN' });
  });

  test('上层保留已核验的具体子阶段，未知子阶段使用宿主证据', () => {
    const child = new LocalPoolStartupError('tls_probe', 'RAW_HEADERS_MISMATCH');
    expect(new LocalPoolStartupError('forwarder_start', child).startup).toEqual(child.startup);
    expect(new LocalPoolStartupError('driver_start', new LocalPoolStartupError('unknown', 'CHANNEL_CLOSED')).startup).toEqual({ stage: 'driver_start', failureCode: 'CHANNEL_CLOSED' });
  });

  test.each([decodeForwarderFrame, decodeLocalDriverFrame])('fatal 兼容旧帧且剔除原始消息及扩展字段', decode => {
    expect(decode(JSON.stringify({ type: 'fatal', message: secret }))).not.toHaveProperty('startup');
    const frame = decode(JSON.stringify({ type: 'fatal', message: secret, raw: secret, startup: { stage: 'certificate', failureCode: 'ENOENT', raw: secret } }));
    expect(frame).toHaveProperty('startup', { stage: 'certificate', failureCode: 'ENOENT' });
    expect(JSON.stringify(frame)).not.toContain(secret);
    expect(decode(JSON.stringify({ type: 'fatal', message: '', startup: { stage: secret, failureCode: secret } }))).toHaveProperty('startup', { stage: 'unknown', failureCode: 'UNKNOWN' });
  });

  test.each([
    ['CHANNEL_CLOSED', ''],
    ['CHANNEL_TRUNCATED', JSON.stringify({ secret })],
    ['CHANNEL_INVALID', JSON.stringify({ secret }) + '\n'],
  ] as const)('实际私有通道保留 %s 而不保留原始帧', async (code, output) => {
    const child = new PrivateProcess([process.execPath, '-e', 'process.stdout.write(' + JSON.stringify(output) + ')'], {}, () => { throw new Error(secret); });
    try {
      const error = await child.next().catch(error => error);
      expect(error).toBeInstanceOf(PrivateProcessError); expect(error.code).toBe(code); expect(error.message).not.toContain(secret);
    } finally { await child.close(); }
  });

  test('实际就绪超时有固定代码，随后仅关闭自己的子进程', async () => {
    const child = new PrivateProcess([process.execPath, '-e', 'process.stdin.resume();process.stdin.once("data",()=>process.exit(0))'], {}, JSON.parse);
    try { await expect(child.next(20)).rejects.toMatchObject({ code: 'CHANNEL_TIMEOUT' }); }
    finally { await child.close(); }
    expect(await child.child.exited).toBe(0);
  });
});
