import { mkdir, mkdtemp, readFile, readlink, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { parseInput } from '../src/shared/input';
import { prepareInput } from '../src/control/header-policy';
import { verifyBinary } from '../src/runtime/profile';
import { isObject } from '../src/shared/errors';
import { decodeWorkerFrame } from '../src/shared/protocol';

const REFERENCE_SHA = '8484c4c58f4b7782a190f7cab7c8aa5d1f706ae26b2d2a5cafe81af070f0611b';
const input = { model: 'claude-sonnet-4-6', max_tokens: 128, stream: true, output_config: { effort: 'low' }, messages: [{ role: 'user', content: 'Print integers.' }] };
const responseEvents = [
  { type: 'message_start', message: { id: 'msg_local', type: 'message', role: 'assistant', model: input.model, content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 1, output_tokens: 0 } } },
  { type: 'content_block_start', index: 0, content_block: { type: 'text', text: '' } },
  { type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: 'ok' } },
  { type: 'content_block_stop', index: 0 },
  { type: 'message_delta', delta: { stop_reason: 'end_turn', stop_sequence: null }, usage: { output_tokens: 1 } },
  { type: 'message_stop' },
];
const responseBody = responseEvents.map(event => 'event: ' + event.type + '\ndata: ' + JSON.stringify(event) + '\n\n').join('');

/** 一次新进程及六轮串行作业的原始性能样本。 */
interface Sample {
  variant: 'compact' | 'reference';
  trial: number;
  pid: number;
  ready_ms: number;
  startup_to_first_complete_ms: number;
  ready_to_first_complete_ms: number;
  jobs: { elapsed_ms: number; upstream_requests: number; response_bytes: number; outbound_json_bytes: number; system_json_bytes: number; declared_tools: number | null }[];
  rss_ready: number;
  rss_after: number;
  rss_peak: number;
  generated_disk_bytes: number;
  executable: string;
  image_sha256: string;
}

async function hash(path: string): Promise<string> {
  const value = createHash('sha256');
  for await (const bytes of createReadStream(path)) value.update(bytes);
  return value.digest('hex');
}

async function disk(path: string): Promise<number> {
  let bytes = 0;
  for (const item of await readdir(path, { withFileTypes: true })) {
    const child = join(path, item.name);
    if (item.isDirectory()) bytes += await disk(child);
    else if (item.isFile()) bytes += (await stat(child)).size;
  }
  return bytes;
}

async function memory(pid: number): Promise<{ rss: number; peak: number }> {
  const status = await readFile('/proc/' + pid + '/status', 'utf8');
  return { rss: Number(/^VmRSS:\s+(\d+)/m.exec(status)?.[1] ?? 0) * 1024, peak: Number(/^VmHWM:\s+(\d+)/m.exec(status)?.[1] ?? 0) * 1024 };
}

async function* readFrames(stream: ReadableStream<Uint8Array>, decode?: (line: string) => unknown): AsyncGenerator<{ at: number; frame: Record<string, unknown> }> {
  const reader = stream.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let pending = '';
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      pending += decoder.decode(next.value, { stream: true });
      if (Buffer.byteLength(pending) > 24 * 1024 * 1024) throw new Error('性能协议帧超限');
      let index: number;
      while ((index = pending.indexOf('\n')) >= 0) {
        const line = pending.slice(0, index); pending = pending.slice(index + 1);
        const frame: unknown = decode ? decode(line) : JSON.parse(line);
        if (!isObject(frame) || typeof frame.type !== 'string') throw new Error('性能协议帧格式错误');
        yield { at: performance.now(), frame };
      }
    }
    throw new Error('性能工作进程在终态前退出');
  } finally { reader.releaseLock(); }
}

async function nextFrame(iterator: ReturnType<typeof readFrames>): Promise<{ at: number; frame: Record<string, unknown> }> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const result = await Promise.race([iterator.next(), new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('性能工作进程超时')), 25000); })]);
    if (result.done) throw new Error('性能工作进程没有返回完整帧');
    return result.value;
  } finally { if (timer) clearTimeout(timer); }
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle]! : (sorted[middle - 1]! + sorted[middle]!) / 2;
}

/** 在无外网的同机回环环境交错测量固定运行时。
 * @param args --binary、--reference 和 --output 明确指定的文件路径。
 * @return 原始样本、三项比值、内存及额外空间已写入；未达标时明确失败。
 */
export async function benchmarkRuntime(args: string[]): Promise<void> {
  if (process.env.CCRB_BENCH_ISOLATED !== '1') {
    const child = Bun.spawn(['unshare', '--net', process.execPath, resolve(import.meta.path), ...args], { env: { PATH: process.env.PATH ?? '/usr/bin:/bin', CCRB_BENCH_ISOLATED: '1' }, stdin: 'ignore', stdout: 'inherit', stderr: 'inherit' });
    if (await child.exited !== 0) throw new Error('隔离性能对照未通过');
    return;
  }
  const options = new Map<string, string>();
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i], value = args[i + 1];
    if (!key || !['--binary', '--reference', '--output'].includes(key) || !value || options.has(key)) throw new Error('必须指定 --binary、--reference、--output');
    options.set(key, resolve(value));
  }
  const binary = options.get('--binary'), reference = options.get('--reference'), output = options.get('--output');
  if (!binary || !reference || !output) throw new Error('性能对照缺少显式文件路径');
  await verifyBinary(binary);
  if (await hash(reference) !== REFERENCE_SHA) throw new Error('vm2api 标杆身份不匹配');
  if (Bun.spawnSync(['ip', 'link', 'set', 'lo', 'up']).exitCode !== 0) throw new Error('不能启用隔离回环网络');
  await mkdir(output, { recursive: true });
  const root = await mkdtemp(join(tmpdir(), 'ccrb-benchmark-'));
  const observed: Record<string, unknown>[] = [];
  const upstream = Bun.serve({ hostname: '127.0.0.1', port: 0, async fetch(request) {
    if (!new URL(request.url).pathname.startsWith('/v1/messages')) return Response.json({});
    const body = await request.json() as Record<string, unknown>;
    observed.push(body);
    return new Response(responseBody, { headers: { 'content-type': 'text/event-stream', 'content-length': String(Buffer.byteLength(responseBody)) } });
  } });
  const samples: Sample[] = [];
  const conditions = { isolation: 'unshare --net，仅启用回环；合成 API key；每进程独立 HOME/config/cwd', trials: 5, jobs_per_process: 6, reference_slots: 20, slots_used: 1, order: '每轮两方交错，奇偶轮反转顺序', page_cache: '未清理，不等同冷磁盘或虚拟机启动', endpoint: '相同本地 HTTP SSE 上游，原生 CCH 由另行 TLS 回归验证', boundary: '从 CLI 运行时启动到协议终态及空闲确认；不包含 HTTP 控制面和模型推理', input, response_bytes: Buffer.byteLength(responseBody), process_loadavg_before: (await readFile('/proc/loadavg', 'utf8')).trim() };
  try {
    for (let trial = 0; trial < 5; trial++) {
      const order = trial % 2 ? ['reference', 'compact'] as const : ['compact', 'reference'] as const;
      for (const variant of order) {
        const home = join(root, variant + '-' + trial), config = join(home, 'config');
        await mkdir(config, { recursive: true });
        await writeFile(join(config, '.claude.json'), JSON.stringify({ userID: 'a'.repeat(64) }));
        const initialDisk = await disk(home);
        const workerId = randomUUID();
        const env = { HOME: home, CLAUDE_CONFIG_DIR: config, PATH: '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', LANG: 'C.UTF-8', ANTHROPIC_API_KEY: 'offline-fixture-key', ANTHROPIC_BASE_URL: 'http://127.0.0.1:' + upstream.port, NO_PROXY: '127.0.0.1,localhost', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1', DISABLE_AUTOUPDATER: '1', DISABLE_AUTO_COMPACT: '1', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', CLAUDE_CODE_NATIVE_SLOTS: '20', CCRB_WORKER_ID: workerId, CLAUDE_CODE_ENTRYPOINT: 'cli', CLAUDE_CODE_GATEWAY_HINT_HEADERS: '1' };
        const requests = Array.from({ length: 6 }, (_, index) => {
          const id = 'bench-' + trial + '-' + index;
          return variant === 'compact' ? { type: 'request_start', schema_version: 2, worker_id: workerId, request_id: id, prepared: prepareInput(parseInput({ request_id: id, body: input })) } : { type: 'job_start', job_id: id, slot_id: '', request: input };
        });
        const started = performance.now();
        const child = Bun.spawn([variant === 'compact' ? binary : reference], { env, cwd: home, stdin: 'pipe', stdout: 'pipe', stderr: 'pipe' });
        const diagnostics = (async () => { const reader = child.stderr.getReader(); while (!(await reader.read()).done) {} })();
        const iterator = readFrames(child.stdout, variant === 'compact' ? line => decodeWorkerFrame(line, workerId) : undefined);
        let peak = 0;
        const poll = setInterval(() => { void memory(child.pid).then(value => { peak = Math.max(peak, value.peak); }).catch(() => {}); }, 10);
        try {
          let readyAt = 0;
          const slots = new Set<string>();
          let hostReady = false;
          while (!readyAt) {
            const { at, frame } = await nextFrame(iterator);
            if (variant === 'compact') {
              if (frame.type === 'worker_error') throw new Error('精简运行时配置失败：' + String(frame.error));
              if (frame.type !== 'worker_ready' || frame.worker_id !== workerId || frame.pid !== child.pid || frame.version !== '2.1.293') throw new Error('精简运行时握手不匹配');
              readyAt = at;
            } else {
              if (frame.type === 'host_ready') { if (frame.slots !== 20) throw new Error('标杆槽位数不匹配'); hostReady = true; }
              if (frame.type === 'slot_ready') {
                if (typeof frame.slot_id !== 'string' || !frame.slot_id) throw new Error('标杆槽位 ID 无效');
                slots.add(frame.slot_id);
              }
              if (hostReady && slots.size === 20) readyAt = at;
            }
          }
          const readyMemory = await memory(child.pid);
          const jobs: Sample['jobs'] = [];
          let firstAt = 0;
          for (let index = 0; index < 6; index++) {
            const job = requests[index]!;
            if (variant === 'reference') (job as { slot_id: string }).slot_id = [...slots][0]!;
            const before = observed.length;
            const sent = performance.now();
            child.stdin.write(JSON.stringify(job) + '\n');
            let terminal = false;
            let responseBytes = 0;
            const chunks: Buffer[] = [];
            const events: unknown[] = [];
            let completedAt = 0;
            while (!completedAt) {
              const { at, frame } = await nextFrame(iterator);
              if (variant === 'compact') {
                if (frame.worker_id !== workerId || frame.request_id !== 'bench-' + trial + '-' + index) throw new Error('精简性能事件跨请求');
                if (frame.type === 'request_event') {
                  const payload = frame.payload;
                  if (!isObject(payload)) throw new Error('精简性能载荷缺失');
                  if (payload.type === 'response_chunk') {
                    if (typeof payload.data_b64 !== 'string') throw new Error('精简性能响应片段无效');
                    const bytes = Buffer.from(payload.data_b64, 'base64'); chunks.push(bytes); responseBytes += bytes.length;
                  }
                  if (payload.type === 'error' || payload.type === 'completed' && payload.state !== 'success') throw new Error('精简性能请求失败');
                  if (payload.type === 'completed') { if (terminal) throw new Error('精简性能请求双终态'); terminal = true; }
                } else if (frame.type === 'worker_idle') {
                  if (!terminal) throw new Error('精简性能请求缺少终态');
                  completedAt = at;
                } else throw new Error('精简性能协议出现未知帧');
              } else {
                if (frame.job_id !== 'bench-' + trial + '-' + index) continue;
                if (frame.type === 'stream_event') {
                  if (!isObject(frame.event)) throw new Error('标杆响应事件缺少载荷');
                  // 标杆会把出站头等诊断包装成 stream_event；这些参与计时，但不是 SSE 正文。
                  if (!['kin_outbound_headers', 'response_headers'].includes(String(frame.event.type))) events.push(frame.event);
                }
                if (frame.type === 'job_error') throw new Error('标杆性能请求失败');
                if (frame.type === 'job_done') completedAt = at;
              }
            }
            if (variant === 'compact' && Buffer.concat(chunks).toString('utf8') !== responseBody) throw new Error('精简性能响应字节不一致');
            if (variant === 'reference' && JSON.stringify(events) !== JSON.stringify(responseEvents)) {
              await writeFile(join(output, 'reference-event-mismatch.json'), JSON.stringify({ actual: events, expected: responseEvents }, null, 2));
              throw new Error('标杆性能响应事件不一致');
            }
            if (observed.length - before !== 1) throw new Error('性能请求出现重放或漏发');
            const actual = observed.at(-1)!;
            if (actual.model !== input.model || actual.max_tokens !== input.max_tokens || actual.stream !== true || !JSON.stringify(actual.messages).includes('Print integers.')) throw new Error('性能请求输入语义不同');
            jobs.push({ elapsed_ms: completedAt - sent, upstream_requests: observed.length - before, response_bytes: variant === 'compact' ? responseBytes : Buffer.byteLength(responseBody),
              outbound_json_bytes: Buffer.byteLength(JSON.stringify(actual)), system_json_bytes: Buffer.byteLength(JSON.stringify(actual.system ?? null)), declared_tools: Array.isArray(actual.tools) ? actual.tools.length : null });
            if (!index) firstAt = completedAt;
            await Bun.sleep(10);
          }
          const afterMemory = await memory(child.pid);
          const sample: Sample = { variant, trial, pid: child.pid, ready_ms: readyAt - started, startup_to_first_complete_ms: firstAt - started, ready_to_first_complete_ms: firstAt - readyAt, jobs, rss_ready: readyMemory.rss, rss_after: afterMemory.rss, rss_peak: Math.max(peak, afterMemory.peak), generated_disk_bytes: (await disk(home)) - initialDisk, executable: await readlink('/proc/' + child.pid + '/exe'), image_sha256: await hash('/proc/' + child.pid + '/exe') };
          samples.push(sample);
          await writeFile(join(output, 'samples.json'), JSON.stringify({ conditions, samples }, null, 2));
          console.log(JSON.stringify({ variant, trial, startup_to_first_complete_ms: sample.startup_to_first_complete_ms, first_ms: sample.ready_to_first_complete_ms, warm_ms: median(jobs.slice(1).map(job => job.elapsed_ms)) }));
        } finally {
          clearInterval(poll);
          child.kill('SIGKILL');
          await child.exited;
          await diagnostics;
          await iterator.return(undefined);
        }
      }
    }
    const summary = Object.fromEntries(['compact', 'reference'].map(variant => {
      const rows = samples.filter(row => row.variant === variant);
      return [variant, { startup_to_first_complete_ms: median(rows.map(row => row.startup_to_first_complete_ms)), ready_to_first_complete_ms: median(rows.map(row => row.ready_to_first_complete_ms)), warm_ms: median(rows.flatMap(row => row.jobs.slice(1).map(job => job.elapsed_ms))), rss_after_bytes: median(rows.map(row => row.rss_after)), rss_peak_bytes: median(rows.map(row => row.rss_peak)), generated_disk_bytes: median(rows.map(row => row.generated_disk_bytes)) }];
    }));
    const ratios = Object.fromEntries(['startup_to_first_complete_ms', 'ready_to_first_complete_ms', 'warm_ms'].map(key => [key, (summary.compact! as Record<string, number>)[key]! / (summary.reference! as Record<string, number>)[key]!]));
    const passed = Object.values(ratios).every(value => value <= 1.10);
    await writeFile(join(output, 'summary.json'), JSON.stringify({ passed, binary_sha256: await hash(binary), reference_sha256: REFERENCE_SHA, summary, ratios, upstream_requests: observed.length, conditions }, null, 2));
    console.log(JSON.stringify({ passed, summary, ratios }));
    if (!passed) throw new Error('至少一项耗时超过标杆的 1.10 倍，性能目标未达标');
  } finally { await upstream.stop(true); await rm(root, { recursive: true, force: true }); }
}

if (import.meta.main) await benchmarkRuntime(process.argv.slice(2));
