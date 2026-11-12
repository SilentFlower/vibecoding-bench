import { createHash } from 'node:crypto';
import { open, realpath, stat, type FileHandle } from 'node:fs/promises';
import { createReadStream, type BigIntStats } from 'node:fs';
import { PROFILE_293 } from './293/source-profile';
import { COMPACT_RUNTIMES } from './compact-profile';

export { PROFILE_293 } from './293/source-profile';

/** 固定来源、分发文件与实际执行体的独立身份。 */
export interface RuntimeIdentity {
  kind: 'original' | 'memfd';
  launcherSha256: string;
  imageSha256: string;
  imageBytes: number;
}

/** 已打开并核验的文件，供启动时绑定确切 inode。 */
export interface VerifiedRuntime {
  handle: FileHandle;
  stamp: string;
  identity: RuntimeIdentity;
}

function stamp(path: string, value: BigIntStats): string {
  return [path, value.dev, value.ino, value.size, value.mtimeNs, value.ctimeNs].join(':');
}

/** 只读文件身份，正常复用无需重新读取全部运行时。
 * @param path 显式运行时路径。
 * @return 真实路径及设备、inode、大小和纳秒时间戳。
 */
export async function runtimeFileStamp(path: string): Promise<string> {
  const actual = await realpath(path);
  return stamp(actual, await stat(actual, { bigint: true }));
}

/** 独立核对加载器实际执行的内存载荷，每次新进程只执行一次。
 * @param pid 刚完成握手的物理进程。
 * @param identity 已授信的分发与执行体身份。
 * @return 实际执行体大小及 SHA256 均与登记值一致。
 */
export async function verifyExecutionImage(pid: number, identity: RuntimeIdentity): Promise<void> {
  if (identity.kind !== 'memfd') return;
  const path = '/proc/' + pid + '/exe';
  if ((await stat(path)).size !== identity.imageBytes) throw new Error('实际执行载荷大小不匹配');
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  if (hash.digest('hex') !== identity.imageSha256) throw new Error('实际执行载荷校验不匹配');
}

/** 核验完整分发文件并保留打开的文件描述符。
 * @param path 运行时路径。
 * @return 真实身份和文件句柄；调用者必须关闭句柄。
 */
export async function verifyRuntime(path: string): Promise<VerifiedRuntime> {
  const actual = await realpath(path);
  const handle = await open(actual, 'r');
  try {
    const before = stamp(actual, await handle.stat({ bigint: true }));
    const hash = createHash('sha256');
    for await (const chunk of handle.createReadStream({ autoClose: false, start: 0 })) hash.update(chunk);
    const digest = hash.digest('hex');
    const compact = COMPACT_RUNTIMES.find(value => value.launcherSha256 === digest);
    if (digest !== PROFILE_293.sha256 && !compact) throw new Error('运行时二进制校验不匹配，仅支持已验证的 2.1.293 来源产物');
    if (stamp(actual, await handle.stat({ bigint: true })) !== before || await runtimeFileStamp(path) !== before) throw new Error('运行时文件在校验期间改变');
    const identity: RuntimeIdentity = compact ? { kind: 'memfd', ...compact } : { kind: 'original', launcherSha256: digest, imageSha256: digest, imageBytes: Number((await handle.stat()).size) };
    return { handle, stamp: before, identity };
  } catch (error) {
    await handle.close();
    throw error;
  }
}

/** 不执行程序，仅核对已授信的完整二进制。
 * @param path 显式程序路径。
 * @return 实际执行体的固定 SHA256。
 */
export async function verifyBinary(path: string): Promise<string> {
  const verified = await verifyRuntime(path);
  try { return verified.identity.imageSha256; } finally { await verified.handle.close(); }
}
