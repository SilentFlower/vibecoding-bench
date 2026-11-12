import { expect, test } from 'bun:test';
import { createHash, generateKeyPairSync, verify } from 'node:crypto';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { sealRuntimeRelease } from '../../scripts/seal-runtime-release';
import { PROFILE_293 } from '../../src/runtime/293/source-profile';

test('发布附件签署确切清单字节，拒绝改变后的构建文件', async () => {
  const root = await mkdtemp(join(tmpdir(), 'ccrb-release-test-'));
  try {
    const { privateKey, publicKey } = generateKeyPairSync('ed25519');
    const binary = join(root, 'launcher'), key = join(root, 'private.pem'), output = join(root, 'release');
    const payload = '合成分发体';
    const digest = createHash('sha256').update(payload).digest('hex');
    await writeFile(binary, payload);
    await writeFile(key, privateKey.export({ type: 'pkcs8', format: 'pem' }), { mode: 0o600 });
    await writeFile(binary + '.manifest.json', JSON.stringify({
      schema_version: 1, source: { version: PROFILE_293.version, sha256: PROFILE_293.sha256 },
      launcher: { bytes: Buffer.byteLength(payload), sha256: digest },
      image: { bytes: 112839864, sha256: 'a'.repeat(64) },
    }));
    const result = await sealRuntimeRelease('v0.1.0-beta.4', binary, key, output);
    const bytes = await readFile(join(output, 'runtime-release.json'));
    const signature = await readFile(join(output, 'runtime-release.sig'));
    expect(verify(null, bytes, publicKey, signature)).toBe(true);
    expect(verify(null, Buffer.concat([bytes, Buffer.from(' ')]), publicKey, signature)).toBe(false);
    expect(result.launcher_sha256).toBe(digest);
    expect(await readFile(join(output, 'ccrb-runtime-linux-x64'), 'utf8')).toBe(payload);
    await writeFile(binary, Buffer.alloc(Buffer.byteLength(payload), 'z'));
    await expect(sealRuntimeRelease('v0.1.0-beta.4', binary, key, join(root, 'bad'))).rejects.toThrow('分发文件摘要不符');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
