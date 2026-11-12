import { join } from 'node:path';
import { readFile } from 'node:fs/promises';
import type { JsonObject, HeaderPair } from '../../src/shared/contracts';
import type { BodySample, PoolPrepared } from './pool-common';

/** 报告中每个位置都有独立来源和表示。 */
export interface ReportStage { source: string; representation: string; body: BodySample; headers: HeaderPair[] }
/** 场景报告不会用前一个阶段填补缺失的最终采集。 */
export interface PoolCaseReport {
  id: string; fixture: string; cachePolicy: string; passed: boolean; checks: { name: string; passed: boolean }[];
  context: JsonObject | null; elapsedMs: number; state: string; bridgeStatus: number;
  ingress: ReportStage; ccPrepared: ReportStage | null;
  ccFinal: (ReportStage & { method: string; path: string; httpVersion: string; cch: { actual: string; expected: string } | null; capturedAt: string }) | null;
  forwarding: { attempted: boolean; outcome: string; upstreamStatus: number | null; localStatus: number; failureCode: string | null; error: string | null } | null;
  poolPrepared: (PoolPrepared & { source: string; representation: string }) | null;
  poolResponse: (ReportStage & { statusCode: number; outcome: string; attempted: boolean }) | null;
  bridgeResponse: ReportStage; note: string | null;
}
/** 测试专用报告，不改变产品 nativeFinalCapture 的语义。 */
export interface PoolReport {
  schemaVersion: 1; createdAt: string; mode: 'live' | 'offline'; model: string; baseUrl: string;
  binary: { path: string; distributionSha256: string; executionSha256: string; kind: string };
  environment: JsonObject; calls: number; budget: number; stopped: string | null; cases: PoolCaseReport[];
}

const escape = (value: string): string => value.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

/** 将已脱敏数据安全生成为静态文本页。 @param report 测试报告。 @return 可离线查看的完整 HTML。 */
export function renderPoolReport(report: PoolReport): string {
  const raw = (title: string, value: unknown): string => '<details><summary>' + escape(title) + (value === null ? ' · 未采集' : '') + '</summary><pre>' + escape(value === null ? '未采集：没有以中间值或本地错误替代此阶段。' : JSON.stringify(value, null, 2)) + '</pre></details>';
  return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Messages 两段采集报告</title><style>body{font:15px/1.65 system-ui,sans-serif;background:#f3f5f7;color:#17232c;margin:0}main{max-width:1100px;margin:auto;padding:24px;min-width:0}h1{font-size:25px}article,.info{background:white;border:1px solid #d4dce2;border-radius:10px;padding:18px;margin:18px 0}h2{font-size:18px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.7 ui-monospace,monospace;max-height:65vh;overflow:auto;padding:12px;background:#f5f7f9}summary{cursor:pointer;padding:10px 0;font-weight:600}details{border-top:1px solid #e4e9ed}.pass{color:#176239}.fail{color:#9d3024}p,li{overflow-wrap:anywhere}a{color:#245d96}@media(max-width:500px){main{padding:12px}article,.info{padding:12px}}</style><main><h1>Messages 两段采集报告</h1><div class="info"><p>' + (report.mode === 'live' ? '真实池响应 · deepseek-flash' : '离线合成夹具 · 未调用真实池') + ' · 调用 ' + report.calls + ' / ' + report.budget + '</p><p>CC 原生请求 → 独立 Node TLS 采集 → 池 Messages → 真实逻辑响应。池转发参数为客户端组装值；生产最终采集能力仍为未实现。</p><p>此页只读，刷新不发起推理。所有预览已脱敏；哈希对应原始观测字节。<a href="report.json">下载报告 JSON</a></p>' + (report.stopped ? '<p class="fail">已停止：' + escape(report.stopped) + '</p>' : '') + '</div>' + raw('环境与固定运行时', { createdAt: report.createdAt, binary: report.binary, environment: report.environment }) + report.cases.map(row => '<article data-case="' + escape(row.id) + '"><h2>' + escape(row.id) + ' · <span class="' + (row.passed ? 'pass' : 'fail') + '">' + (row.passed ? '验证通过' : '未通过') + '</span></h2><p>HTTP ' + row.bridgeStatus + ' · ' + escape(row.state) + ' · ' + Math.round(row.elapsedMs) + ' ms · 缓存策略 ' + escape(row.cachePolicy) + '</p>' + (row.note ? '<p class="fail">' + escape(row.note) + '</p>' : '') + raw('校验与关联', { checks: row.checks, context: row.context, forwarding: row.forwarding }) + raw('HTTP 入站（合成场景）', row.ingress) + raw('CC 中间值（传输前）', row.ccPrepared) + raw('CC 最终出站（Node TLS 实收、原始头、CCH）', row.ccFinal) + raw('池转发参数（客户端组装，model 已映射）', row.poolPrepared) + raw('池响应（逻辑字节）', row.poolResponse) + raw('调用方响应（逻辑字节）', row.bridgeResponse) + '</article>').join('') + '</main></html>';
}

/** 只开放两份已经保存的报告，任何刷新均不触发测试。 @param directory 独立报告目录。 @param port 回环端口。 @return 可关闭的只读服务。 */
export async function servePoolReport(directory: string, port: number): Promise<Bun.Server<undefined>> {
  const html = await readFile(join(directory, 'index.html')), json = await readFile(join(directory, 'report.json'));
  return Bun.serve({ hostname: '127.0.0.1', port, fetch(request) {
    const url = new URL(request.url);
    if (request.method !== 'GET' || !['127.0.0.1','localhost'].includes(url.hostname)) return new Response('只读本机报告', { status: 403 });
    const content = url.pathname === '/' || url.pathname === '/index.html' ? html : url.pathname === '/report.json' ? json : null;
    return new Response(content ?? '文件不存在', { status: content ? 200 : 404, headers: { 'content-type': url.pathname === '/report.json' ? 'application/json; charset=utf-8' : 'text/html; charset=utf-8', 'cache-control': 'no-store', 'x-content-type-options': 'nosniff', 'content-security-policy': "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'" } });
  } });
}
