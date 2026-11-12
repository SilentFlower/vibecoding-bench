import { PoolIncidentCollector, PoolIncidentError, poolIncidentCode } from './testing/local-pool-incidents';

/** 解析只读补采参数，不接受目标地址或真实凭据。
 * @param args 有限的本地运行与输出参数。
 * @return 已校验的显式输入；非法参数只返回固定错误。
 */
function readArguments(args: string[]): { runId: string; directory: string; requestId?: string; output?: string } {
  const values = new Map<string, string>();
  for (let index = 0; index < args.length; index += 2) {
    const key = args[index], value = args[index + 1];
    if (!key || !['--run', '--run-dir', '--request-id', '--output'].includes(key) || !value || values.has(key)) throw new PoolIncidentError('SOURCE_INVALID');
    values.set(key, value);
  }
  const runId = values.get('--run') ?? '', directory = values.get('--run-dir') ?? '', requestId = values.get('--request-id');
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(runId) || !directory || requestId !== undefined && !/^[A-Za-z0-9_-]{1,128}$/.test(requestId)) throw new PoolIncidentError('SOURCE_INVALID');
  return { runId, directory, requestId, output: values.get('--output') };
}

if (import.meta.main) {
  let collector: PoolIncidentCollector | undefined;
  try {
    const options = readArguments(process.argv.slice(2));
    collector = await PoolIncidentCollector.open(options);
    const status = await collector.collect(options.requestId);
    process.stdout.write(JSON.stringify(status, null, 2) + '\n');
    if (status.codes.length) process.exitCode = 1;
  } catch (error) {
    process.stderr.write('本地池取证失败：' + poolIncidentCode(error) + '\n'); process.exitCode = 1;
  } finally {
    try { await collector?.close(false); }
    catch { process.stderr.write('本地池取证失败：UNKNOWN\n'); process.exitCode = 1; }
  }
}
