import { chmod, copyFile, mkdir, mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { constants, createReadStream } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { PROFILE_293 } from '../src/runtime/293/source-profile';

const LIMIT_BYTES = 27933052;
const TOOL_SHA = 'd32657a7a0e4cdc0a8aa57cafe474746944d76e861e753e9c902b9c9356fa886';
const SDK_SHA = '0b6080b8c3e7a579161d2d495224c0e51c467576cb4c7048b0ab485ef44cc22e';
const TOOL_ARCHIVE_SHA = '22cf82fcc6eb7474f1d5bb4f02c0f8ebd573a718089d6833dc30f8350a3b232e';
const RELEASE = 'https://github.com/ip7z/7zip/releases/download/26.05/';
const project = resolve(import.meta.dir, '..');
const BRIDGE_SOURCES = ['src/runtime/293/source-profile.ts', 'src/runtime/293/native.ts', 'src/runtime/293/cli.ts', 'src/runtime/293/static-text.ts', 'src/runtime/293/job.ts', 'src/runtime/293/worker.ts', 'src/runtime/293/telemetry.ts', 'src/shared/contracts.ts', 'src/shared/protocol.ts', 'src/shared/upstream.ts', 'src/shared/errors.ts', 'src/shared/input.ts', 'src/shared/native-input.ts', 'src/shared/native-classifier.ts', 'src/shared/request-attribution.ts', 'src/shared/runtime-policy.ts', 'src/shared/cache-policy.ts', 'src/control/header-policy.ts', 'src/control/redaction.ts', 'scripts/runtime/compile.ts', 'scripts/runtime/static-prompts.ts', 'scripts/runtime/image.py', 'scripts/runtime/loader.c', 'scripts/build-runtime.ts'];

async function digest(path: string): Promise<string> {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest('hex');
}

async function download(url: string, path: string, expected: string): Promise<void> {
  const response = await fetch(url, { signal: AbortSignal.timeout(60000) });
  if (!response.ok) throw new Error('固定工具下载失败：HTTP ' + response.status);
  await Bun.write(path, response);
  if (await digest(path) !== expected) throw new Error('固定工具归档校验不匹配');
}

async function run(args: string[], cwd: string, env?: Record<string, string>): Promise<string> {
  const child = Bun.spawn(args, { cwd, env, stdin: 'ignore', stdout: 'pipe', stderr: 'pipe' });
  const [stdout, stderr, code] = await Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited]);
  if (code !== 0) throw new Error('构建步骤失败：' + args[0] + '，退出码=' + code + '，' + stderr.split('\n').filter(line => line.length < 400).slice(-4).join('\n'));
  return stdout;
}

/** 从固定官方来源构建单文件桥接运行时，源程序及提取内容不会进入输出。
 * @param args 显式 --source、--out，可选 --sevenzip、--sdk 固定工具路径。
 * @return 产物与可核对的构建清单已写入，所有临时内容已清理。
 */
export async function buildRuntime(args: string[]): Promise<void> {
  if (process.platform !== 'linux' || process.arch !== 'x64') throw new Error('此固定配方只支持 Linux x64');
  const options = new Map<string, string>();
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i], value = args[i + 1];
    if (!key || !['--source', '--out', '--sevenzip', '--sdk'].includes(key) || !value || value.startsWith('--') || options.has(key)) throw new Error('用法：bun scripts/build-runtime.ts --source 官方程序 --out 新产物 [--sevenzip 7zz] [--sdk 源归档]');
    options.set(key, resolve(value));
  }
  const source = options.get('--source'), output = options.get('--out');
  if (!source || !output) throw new Error('必须显式提供 --source 和 --out');
  if (await digest(source) !== PROFILE_293.sha256) throw new Error('固定官方源程序校验不匹配');
  if (await Bun.file(output).exists() || await Bun.file(output + '.manifest.json').exists()) throw new Error('输出已存在，不能覆盖原版或其它产物');
  const root = await mkdtemp(join(tmpdir(), 'ccrb-build-'));
  try {
    const bridgeSources = Object.fromEntries(await Promise.all(BRIDGE_SOURCES.map(async path => [path, await digest(join(project, path))])));
    const home = join(root, 'home');
    await mkdir(home);
    const environment = { HOME: home, PATH: process.env.PATH ?? '/usr/bin:/bin', LANG: 'C.UTF-8', CLAUDE_CONFIG_DIR: home,
      CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', DISABLE_AUTOUPDATER: '1', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1' };
    const isolated = (command: string[], env: Record<string, string> = environment): Promise<string> => run(['unshare', '--net', ...command], root, env);
    console.log('核验并提取固定 293 来源');
    await isolated(['python3', join(project, 'scripts/runtime/image.py'), 'extract', source, join(root, 'modules'), PROFILE_293.sha256]);
    const compiledDriver = await Bun.build({ entrypoints: [join(project, 'scripts/runtime/compile.ts')], target: 'bun', format: 'esm', outdir: root, naming: 'compiler.mjs' });
    if (!compiledDriver.success) throw new Error('构建驱动打包失败');
    console.log('以原版 Bun 1.4.3 编译专用常驻入口');
    await isolated([source, '--version'], { ...environment, BUN_OPTIONS: '--preload ' + join(root, 'compiler.mjs'), CCRB_BUILD_ROOT: root, CCRB_BUILD_SOURCE: source, CCRB_BUILD_PROJECT: project });
    await isolated(['python3', join(project, 'scripts/runtime/image.py'), 'prune', join(root, 'ccrb-worker'), join(root, 'ccrb-runtime.image'), join(root, 'image.json')]);
    const image: { image_sha256: string; image_bytes: number; kernel_before: Record<string, string>; icu_kept: number; icu_removed: number; locale_policy: string } = JSON.parse(await readFile(join(root, 'image.json'), 'utf8'));
    let sevenzip = options.get('--sevenzip');
    if (!sevenzip) {
      const archive = join(root, '7zip-tool.tar.xz');
      await download(RELEASE + '7z2605-linux-x64.tar.xz', archive, TOOL_ARCHIVE_SHA);
      await mkdir(join(root, '7zip-tool'));
      await run(['tar', '-xf', archive, '-C', join(root, '7zip-tool')], root);
      sevenzip = join(root, '7zip-tool/7zz');
    }
    if (await digest(sevenzip) !== TOOL_SHA) throw new Error('7-Zip 工具校验不匹配');
    let sdkArchive = options.get('--sdk');
    if (!sdkArchive) {
      sdkArchive = join(root, '7zip-sdk.tar.xz');
      await download(RELEASE + '7z2605-src.tar.xz', sdkArchive, SDK_SHA);
    }
    if (await digest(sdkArchive) !== SDK_SHA) throw new Error('7-Zip SDK 校验不匹配');
    const sdkRoot = join(root, 'sdk');
    await mkdir(sdkRoot);
    await run(['tar', '-xf', sdkArchive, '-C', sdkRoot], root);
    const archive = join(root, 'payload.7z');
    const packOptions = ['-t7z', '-mx=9', '-m0=BCJ2', '-m1=LZMA2:d=128m:fb=273', '-m2=LZMA2:d=16m', '-m3=LZMA2:d=16m', '-mb0:1', '-mb0s1:2', '-mb0s2:3', '-mmt=1', '-mtm=off', '-mta=off', '-mtc=off', '-bsp0'];
    console.log('按固定英语环境裁剪 ICU 并压缩完整执行体');
    await isolated([sevenzip, 'a', ...packOptions, archive, 'ccrb-runtime.image']);
    await isolated([sevenzip, 't', archive]);
    await writeFile(join(root, 'payload-meta.h'), '#define CCRB_IMAGE_BYTES ' + image.image_bytes + 'ULL\nstatic const unsigned char ccrb_image_sha256[32] = {' + [...Buffer.from(image.image_sha256, 'hex')].join(',') + '};\n');
    await writeFile(join(root, 'payload.s'), '.section .rodata\n.global ccrb_payload_start\n.global ccrb_payload_end\nccrb_payload_start:\n.incbin "payload.7z"\nccrb_payload_end:\n.section .note.GNU-stack,"",@progbits\n');
    const sdk = join(sdkRoot, 'C');
    const sdkFiles = ['Bcj2.c', 'Bra.c', 'Bra86.c', 'BraIA64.c', 'CpuArch.c', 'Delta.c', 'Lzma2Dec.c', 'LzmaDec.c', '7zCrc.c', '7zCrcOpt.c', '7zAlloc.c', '7zArcIn.c', '7zBuf.c', '7zBuf2.c', '7zDec.c', '7zStream.c', 'Sha256.c', 'Sha256Opt.c'];
    const compiler = await run(['gcc', '-dumpfullversion'], root);
    const loader = join(root, 'ccrb-runtime');
    const gccFlags = ['-O3', '-DNDEBUG', '-DZ7_EXTRACT_ONLY', '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror'];
    // 发布分发体可用 ELF Build ID 对照崩溃记录；执行体身份继续取实际 SHA256。
    const linkerFlags = ['-Wl,--gc-sections', '-Wl,--build-id=sha1'];
    await isolated(['gcc', ...gccFlags, '-ffile-prefix-map=' + root + '=/ccrb-build', '-I', sdk, '-I', root, join(project, 'scripts/runtime/loader.c'), join(root, 'payload.s'), ...sdkFiles.map(file => join(sdk, file)), ...linkerFlags, '-s', '-o', loader]);
    const bytes = (await stat(loader)).size;
    if (bytes > LIMIT_BYTES) throw new Error('完整可执行产物超出体积目标：' + bytes + ' > ' + LIMIT_BYTES);
    const launcherSha256 = await digest(loader);
    const closure = JSON.parse(await readFile(join(root, 'closure.json'), 'utf8'));
    const manifest = {
      schema_version: 1, source: { version: PROFILE_293.version, sha256: PROFILE_293.sha256 },
      kernel: { version: closure.bun_version, revision: closure.bun_revision, sections_before_prune: image.kernel_before },
      launcher: { sha256: launcherSha256, bytes }, image: { sha256: image.image_sha256, bytes: image.image_bytes },
      deployment: { files: [{ name: output.split('/').at(-1), bytes, sha256: launcherSha256 }], total_bytes: bytes, limit_bytes: LIMIT_BYTES, required_external_files: [], existing_system_libraries: ['librt.so.1', 'libc.so.6', 'ld-linux-x86-64.so.2', 'libpthread.so.0', 'libdl.so.2', 'libm.so.6'], disk_expansion_bytes: 0, memory_file_bytes: image.image_bytes },
      recipe: { version: 10, bridge_sources: bridgeSources, archive: packOptions, gcc: compiler.trim(), gcc_flags: gccFlags, linker_flags: linkerFlags, tool_sha256: TOOL_SHA, sdk_archive_sha256: SDK_SHA, sdk_files: sdkFiles, icu: { kept: image.icu_kept, removed: image.icu_removed, policy: image.locale_policy } },
      closure,
      admission: '构建通过不自动授信；必须对最终哈希执行原生回归、常驻隔离、部署验证并保留计时记录后登记',
    };
    if (await digest(source) !== PROFILE_293.sha256) throw new Error('官方来源在构建期间改变');
    for (const [path, expected] of Object.entries(bridgeSources)) if (await digest(join(project, path)) !== expected) throw new Error('桥接源码在构建期间改变：' + path);
    await mkdir(dirname(output), { recursive: true });
    await copyFile(loader, output, constants.COPYFILE_EXCL);
    await chmod(output, 0o755);
    await writeFile(output + '.manifest.json', JSON.stringify(manifest, null, 2), { flag: 'wx' });
    console.log(JSON.stringify({ bytes, launcher_sha256: launcherSha256, image_sha256: image.image_sha256 }));
  } finally { await rm(root, { recursive: true, force: true }); }
}

if (import.meta.main) await buildRuntime(process.argv.slice(2));
