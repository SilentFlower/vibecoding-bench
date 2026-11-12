import { chmod, copyFile, mkdir, readFile, readdir, rename, rm, stat, writeFile } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { join, relative, resolve } from 'node:path';
import { TLS_VERIFIER_PROFILE } from '../src/shared/tls-verifier-protocol';

const project = resolve(import.meta.dir, '..');

async function run(args: string[], env?: Record<string, string | undefined>): Promise<string> {
  const child = Bun.spawn(args, { cwd: project, env, stdin: 'ignore', stdout: 'pipe', stderr: 'inherit' });
  const [output, code] = await Promise.all([new Response(child.stdout).text(), child.exited]);
  if (code !== 0) throw new Error('TLS 辅助程序构建失败：' + args[0]);
  return output.trim();
}

async function sources(directory: string, result: Record<string, string>): Promise<void> {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (['target', 'Cargo.lock.initial'].includes(entry.name)) continue;
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await sources(path, result);
    else if (entry.isFile()) result[relative(project, path)] = createHash('sha256').update(await readFile(path)).digest('hex');
  }
}

/** 独立构建验证器，登记来源与实际产物，不自动修改授信清单。
 * @return 构建和来源清单已写入 dist。
 */
export async function buildTlsVerifier(): Promise<void> {
  const compiler = await run(['rustc', '--version']);
  const target = 'x86_64-unknown-linux-gnu';
  if (process.platform !== 'linux' || process.arch !== 'x64') throw new Error('尚未验证此平台的 TLS 辅助程序');
  const flags = '--remap-path-prefix=' + project + '=/ccrb-build';
  const hashes: Record<string, string> = {};
  await sources(join(project, 'native/tls-verifier'), hashes);
  await sources(join(project, 'native/vendor/craftls'), hashes);
  hashes['scripts/build-tls-verifier.ts'] = createHash('sha256').update(await readFile(import.meta.path)).digest('hex');
  await run(['cargo', 'build', '--manifest-path', 'native/tls-verifier/Cargo.toml', '--release', '--locked', '--target', target, '-j', '2'], { PATH: process.env.PATH, HOME: process.env.HOME, LANG: 'C.UTF-8', CARGO_HOME: process.env.CARGO_HOME, RUSTUP_HOME: process.env.RUSTUP_HOME, RUSTUP_TOOLCHAIN: process.env.RUSTUP_TOOLCHAIN, CARGO_TARGET_DIR: join(project, 'native/tls-verifier/target'), CARGO_ENCODED_RUSTFLAGS: flags });
  for (const [path, expected] of Object.entries(hashes)) if (createHash('sha256').update(await readFile(join(project, path))).digest('hex') !== expected) throw new Error('构建期间源码改变：' + path);
  const output = join(project, 'dist/tls-verifier');
  await mkdir(join(project, 'dist'), { recursive: true });
  const staging = output + '.tmp-' + randomUUID();
  try {
    await copyFile(join(project, 'native/tls-verifier/target', target, 'release/ccrb-tls-verifier'), staging);
    await chmod(staging, 0o755);
    // 原子更换路径，已运行辅助程序仍持有原 inode，不能原地截断它的执行映像。
    await rename(staging, output);
  } finally { await rm(staging, { force: true }); }
  const sha256 = createHash('sha256').update(await readFile(output)).digest('hex');
  const manifest = { schema_version: 1, profile: TLS_VERIFIER_PROFILE, recipe: 1, compiler, target, rustflags: flags.replace(project, '<project>'), sources: hashes, binary: { bytes: (await stat(output)).size, sha256 }, admission: '独立辅助程序，非官方 CC TLS 实现；构建不自动授信，需要回环验收并登记 SHA256' };
  await writeFile(output + '.manifest.json', JSON.stringify(manifest, null, 2) + '\n', { mode: 0o600 });
  console.log(JSON.stringify({ profile: manifest.profile, compiler, ...manifest.binary }));
}

if (import.meta.main) await buildTlsVerifier();
