import { createHash, createPrivateKey, sign } from 'node:crypto';
import { constants, createReadStream } from 'node:fs';
import { chmod, copyFile, mkdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { PROFILE_293 } from '../src/runtime/293/source-profile';

const ASSET = 'ccrb-runtime-linux-x64';
const VERSION = /^v0\.1\.0-beta\.[1-9][0-9]{0,8}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const MAX_LAUNCHER_BYTES = 27_933_052;
const MAX_IMAGE_BYTES = 128 * 1024 * 1024;

/** 供 V3 下载端和 sender 独立核验的固定 293 发布清单。 */
interface RuntimeRelease {
  schema_version: 1;
  release: string;
  platform: 'linux-x64';
  asset: typeof ASSET;
  source_version: typeof PROFILE_293.version;
  source_sha256: typeof PROFILE_293.sha256;
  launcher_sha256: string;
  launcher_bytes: number;
  image_sha256: string;
  image_bytes: number;
  worker_schema: 2;
  raw_input_protocol: 1;
  resource_contract: 1;
}

function identity(value: unknown, maxBytes: number): { sha256: string; bytes: number } {
  if (typeof value !== 'object' || value === null || !('sha256' in value) || !('bytes' in value)
      || typeof value.sha256 !== 'string' || !SHA256.test(value.sha256)
      || typeof value.bytes !== 'number' || !Number.isSafeInteger(value.bytes) || value.bytes < 1 || value.bytes > maxBytes) {
    throw new Error('构建产物身份无效');
  }
  return { sha256: value.sha256, bytes: value.bytes };
}

async function verifyLauncher(path: string, expected: { sha256: string; bytes: number }): Promise<void> {
  const actual = await stat(path);
  if (!actual.isFile() || actual.size !== expected.bytes) throw new Error('分发文件大小不符');
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  if (hash.digest('hex') !== expected.sha256) throw new Error('分发文件摘要不符');
}

/** 为已通过离线准入的固定 293 制品生成可上传的三个发布附件。
 * @param release 固定 beta 标签。
 * @param binary 已通过离线行为回归的实际分发文件。
 * @param keyPath 发布端专用 Ed25519 私钥文件。
 * @param output 尚未存在的本地输出目录。
 * @return 完整签署的发布身份。
 */
export async function sealRuntimeRelease(release: string, binary: string, keyPath: string, output: string): Promise<RuntimeRelease> {
  if (!VERSION.test(release)) throw new Error('发布标签必须为 v0.1.0-beta.N');
  const build = JSON.parse(await readFile(binary + '.manifest.json', 'utf8'));
  if (build?.schema_version !== 1 || build.source?.version !== PROFILE_293.version || build.source?.sha256 !== PROFILE_293.sha256) {
    throw new Error('构建清单的固定官方来源不匹配');
  }
  const launcher = identity(build.launcher, MAX_LAUNCHER_BYTES);
  const image = identity(build.image, MAX_IMAGE_BYTES);
  const key = createPrivateKey(await readFile(keyPath));
  if (key.asymmetricKeyType !== 'ed25519') throw new Error('发布签名只接受 Ed25519 私钥');
  await verifyLauncher(binary, launcher);
  const manifest: RuntimeRelease = {
    schema_version: 1, release, platform: 'linux-x64', asset: ASSET,
    source_version: PROFILE_293.version, source_sha256: PROFILE_293.sha256,
    launcher_sha256: launcher.sha256, launcher_bytes: launcher.bytes,
    image_sha256: image.sha256, image_bytes: image.bytes,
    worker_schema: 2, raw_input_protocol: 1, resource_contract: 1,
  };
  const bytes = Buffer.from(JSON.stringify(manifest) + '\n', 'utf8');
  await mkdir(output, { mode: 0o700 });
  try {
    const destination = join(output, ASSET);
    await copyFile(binary, destination, constants.COPYFILE_EXCL);
    await verifyLauncher(destination, launcher);
    await chmod(destination, 0o555);
    await writeFile(join(output, 'runtime-release.sig'), sign(null, bytes, key), { flag: 'wx' });
    await writeFile(join(output, 'runtime-release.json'), bytes, { flag: 'wx' });
  } catch (error) {
    await rm(output, { recursive: true, force: true });
    throw error;
  }
  return manifest;
}

if (import.meta.main) {
  const args = process.argv.slice(2);
  if (args.length !== 4) throw new Error('用法：bun scripts/seal-runtime-release.ts <发布标签> <运行时文件> <Ed25519 私钥文件> <新输出目录>');
  console.log(JSON.stringify(await sealRuntimeRelease(args[0]!, args[1]!, args[2]!, args[3]!)));
}
