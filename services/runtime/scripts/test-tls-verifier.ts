import { build } from './build';
import { buildTlsVerifier } from './build-tls-verifier';

if (process.platform !== 'linux') throw new Error('TLS 验证需要 Linux 网络命名空间');
await build();
await buildTlsVerifier();
const child = Bun.spawn(['unshare', '--net', process.execPath, 'test', 'tests/native/tls-verifier.test.ts', '--timeout', '60000', ...process.argv.slice(2)], { env: { ...process.env, CCRB_NATIVE_ISOLATED: '1', CCRB_TLS_VERIFIER_TEST: '1' }, stdin: 'inherit', stdout: 'inherit', stderr: 'inherit' });
process.exitCode = await child.exited;
