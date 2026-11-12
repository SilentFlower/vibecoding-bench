import { test, expect, type APIRequestContext } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const session = '55555555-5555-4555-8555-555555555555';

/** 创建演示日志并等到异步持久化完成。
 * @param request 页面验收共用的本地 HTTP 客户端。
 * @param id 固定夹具请求标识。
 * @param context 主会话或子代理关联信息。
 * @param model 模型显示内容。
 * @return 记录可被只读接口查询。
 */
async function seed(request: APIRequestContext, id: string, context: Record<string, unknown> = {}, model = 'claude-sonnet-4-6'): Promise<void> {
  const existing = await request.get('/api/logs/' + id);
  if (existing.ok()) { expect((await existing.json()).request.engine).toBe('demo/fixture'); return; }
  const response = await request.post('/api/requests', {
    data: {
      request_id: id, context,
      headers: [['x-future-ui', 'preserved'], ['Authorization', 'Bearer ui-private-canary']],
      body: { model, stream: true, max_tokens: 64, messages: [{ role: 'user', content: '页面离线验收 ui-private-canary' }] },
    },
  });
  expect(response.status()).toBe(200);
  await response.body();
  await expect.poll(async () => {
    const detail = await request.get('/api/logs/' + id);
    return detail.ok() ? (await detail.json()).request.state : 'missing';
  }).toBe('success');
}

test.beforeAll(async ({ request }) => {
  await mkdir('artifacts', { recursive: true });
  await seed(request, 'ui-main', { sessionId: session, agentId: 'root-ui', agentKind: 'main' });
  await seed(request, 'ui-child', { sessionId: session, requestClass: 'subagent', agentId: 'child-ui', parentAgentId: 'root-ui', agentType: 'Explore' });
  await seed(request, 'ui-compact', { requestClass: 'compaction' });
});

test('列表、四页签、脱敏复制和真实采集边界', async ({ page, context }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/');
  await page.getByLabel('每 3 秒刷新').uncheck();
  await expect(page.locator('#engine-badge')).toHaveText('演示模式 · 未调用上游');
  await expect(page.locator('#rows tr')).toHaveCount(3);
  await page.screenshot({ path: 'artifacts/logs-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'ui-main', exact: true }).click();
  const detail = page.getByRole('dialog');
  await expect(detail.getByText('root-ui', { exact: true }).first()).toBeVisible();
  await detail.getByRole('tab', { name: '头部处理', exact: true }).click();
  await expect(detail.getByRole('row').filter({ hasText: 'x-future-ui' })).toContainText('删除');
  await expect(detail.getByRole('row').filter({ hasText: 'x-future-ui' })).toContainText('调用方请求头未登记到协议白名单');
  await expect(detail.getByRole('row').filter({ hasText: 'Authorization' })).toContainText('删除');
  await detail.getByRole('tab', { name: '性能', exact: true }).click();
  await expect(detail.getByText('发送至首个有效输出', { exact: true })).toBeVisible();
  await detail.getByRole('tab', { name: '原始数据', exact: true }).click();
  const body = detail.locator('pre').last();
  await expect(body).toContainText('[REDACTED]');
  await expect(body).not.toContainText('ui-private-canary');
  await detail.getByRole('button', { name: '复制', exact: true }).last().click();
  await expect(detail.getByRole('status')).toHaveText('已复制脱敏内容');
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('[REDACTED]');
  await detail.getByRole('button', { name: /CC 组装（中间值）/ }).click();
  await expect(detail.locator('.capture-meta')).toContainText('demo_fixture');
  await detail.getByRole('button', { name: /最终出站采样/ }).click();
  await expect(detail.locator('.capture-meta')).toContainText('未采集');
  await expect(detail.locator('.section-note')).toContainText('未开启最终出站验证');
  await expect(detail.getByRole('button', { name: '复制', exact: true })).toBeDisabled();
  await page.screenshot({ path: 'artifacts/logs-detail-desktop.png' });
  expect(errors).toEqual([]);
});

test('类别、时间和同会话关联筛选', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('每 3 秒刷新').uncheck();
  await page.getByRole('combobox', { name: '请求类别', exact: true }).selectOption('subagent');
  await page.getByRole('button', { name: '应用筛选', exact: true }).click();
  await expect(page.locator('#rows tr')).toHaveCount(1);
  await page.getByRole('button', { name: 'ui-child', exact: true }).click();
  const detail = page.getByRole('dialog');
  await expect(detail.getByText('child-ui', { exact: true })).toBeVisible();
  await expect(detail.getByText('root-ui', { exact: true })).toBeVisible();
  await detail.getByRole('button', { name: '查看同会话请求', exact: true }).click();
  await expect(page.getByLabel('会话 ID', { exact: true })).toHaveValue(session);
  await expect(page.locator('#rows tr')).toHaveCount(2);
  await page.getByLabel('开始时间', { exact: true }).fill('2099-01-01T00:00');
  await page.getByRole('button', { name: '应用筛选', exact: true }).click();
  await expect(page.locator('#empty')).toBeVisible();
});

test('手机详情可读，原文及模型内容只作为安全文本', async ({ page, request }) => {
  await seed(request, 'ui-xss', {}, '<img src=x onerror="window.ccrbInjected=true">');
  await page.setViewportSize({ width: 390, height: 844 });
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await page.getByLabel('每 3 秒刷新').uncheck();
  await page.getByLabel('请求 ID', { exact: true }).fill('ui-xss');
  await page.getByRole('button', { name: '应用筛选', exact: true }).click();
  await expect(page.locator('#rows tr')).toHaveCount(1);
  await expect(page.locator('#rows img')).toHaveCount(0);
  expect(await page.evaluate(() => 'ccrbInjected' in window)).toBe(false);
  await page.getByRole('button', { name: 'ui-xss', exact: true }).click();
  const detail = page.getByRole('dialog');
  await expect(detail.getByText('<img src=x onerror="window.ccrbInjected=true">', { exact: true })).toHaveCount(3);
  await expect(detail.getByText('<img src=x onerror="window.ccrbInjected=true">', { exact: true }).first()).toBeVisible();
  await detail.getByRole('tab', { name: '原始数据', exact: true }).click();
  await expect(detail.locator('pre').last()).toContainText('<img src=x');
  expect(await detail.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'artifacts/logs-mobile.png', fullPage: true });
  await page.keyboard.press('Escape');
  await expect(detail).not.toBeVisible();
  expect(errors).toEqual([]);
});

test('原生入站显示接入路径和改写中间值', async ({ page, request }) => {
  const response = await request.post('/api/requests', {
    data: {
      request_id: 'ui-native',
      body: {
        model: 'claude-sonnet-4-6',
        system: [{ type: 'text', text: 'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=12345;' }],
        metadata: { user_id: JSON.stringify({ device_id: 'a'.repeat(64), account_uuid: '', session_id: session }) },
        messages: [{ role: 'user', content: '原生页面合同的合成夹具' }],
      },
    },
  });
  expect(response.status()).toBe(200);
  await response.body();
  await expect.poll(async () => (await (await request.get('/api/logs/ui-native')).json()).context?.inputFormat).toBe('claude_code');
  await page.goto('/');
  await page.getByLabel('每 3 秒刷新').uncheck();
  await page.getByRole('button', { name: 'ui-native', exact: true }).click();
  const detail = page.getByRole('dialog');
  await expect(detail.getByText('原生 CC 正文接入', { exact: true })).toBeVisible();
  await detail.getByRole('tab', { name: '原始数据', exact: true }).click();
  await detail.getByRole('button', { name: /原生改写（中间值）/ }).click();
  await expect(detail.locator('.capture-meta')).toContainText('demo_fixture');
  await detail.getByRole('button', { name: /最终出站采样/ }).click();
  await expect(detail.locator('.capture-meta')).toContainText('未采集');
});

test('入口拒绝而未解析的请求显示实际状态', async ({ page, request }) => {
  const response = await request.post('/v1/messages', { data: { model: 'm', messages: [{ role: 'invalid', content: '非法角色的合成输入' }] } });
  expect(response.status()).toBe(400);
  const id = response.headers()['x-ccrb-request-id']!;
  await expect.poll(async () => (await (await request.get('/api/logs/' + id)).json()).request?.state).toBe('error');
  await page.goto('/');
  await page.getByLabel('每 3 秒刷新').uncheck();
  await page.getByTitle(id, { exact: true }).click();
  const detail = page.getByRole('dialog');
  await expect(detail.locator('.detail-grid')).toContainText('接入路径未解析');
  await expect(detail.getByText('旧记录未注明', { exact: true })).toHaveCount(0);
});

test('迟到启动证据可刷新关联，来源、未知和发生时上下文清楚区分', async ({ page, request }) => {
  const linkedSession = '77777777-7777-4777-8777-777777777777';
  await seed(request, 'ui-linked-child', { sessionId: linkedSession, requestClass: 'subagent', agentId: 'linked-child' });
  await page.goto('/'); await page.getByLabel('每 3 秒刷新').uncheck();
  await page.getByTitle('ui-linked-child', { exact: true }).click();
  const detail = page.getByRole('dialog');
  await expect(detail.getByText('关联信息未知', { exact: true })).toBeVisible();
  await expect(detail.getByText('未知（客户端未提供且无可用证据）', { exact: true })).toBeVisible();
  const response = await request.post('/api/requests', { data: {
    request_id: 'ui-launch-evidence', context: { agentKind: 'main', agentId: 'linked-parent', sessionId: linkedSession },
    body: { model: 'fixture', max_tokens: 64, stream: false, system: [{ type: 'text', text: 'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=12345;' }], metadata: { user_id: JSON.stringify({ device_id: 'a'.repeat(64), account_uuid: '', session_id: linkedSession }) }, messages: [
      { role: 'assistant', content: [{ type: 'tool_use', id: 'toolu-ui', name: 'Agent', input: { subagent_type: 'Explore' } }] },
      { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu-ui', content: [{ type: 'text', text: 'Async agent launched successfully. (This tool result is internal metadata — never quote or paste any part of it, including the agentId below, into a user-facing reply.)\nagentId: linked-child (internal ID - do not mention to user.)\n合成启动说明' }] }] },
    ] },
  } });
  expect(response.status()).toBe(200); await response.body();
  await expect.poll(async () => (await (await request.get('/api/logs/ui-linked-child')).json()).agentAssociation?.state).toBe('linked');
  await detail.getByRole('button', { name: '刷新详情', exact: true }).click();
  await expect(detail.getByText('由证据关联', { exact: true })).toBeVisible();
  await expect(detail.getByText('linked-parent', { exact: true })).toBeVisible();
  await expect(detail.getByText('Explore', { exact: true })).toBeVisible();
  await expect(detail.getByText('客户端工具结果', { exact: true })).toHaveCount(2);
  await expect(detail.getByText('发生时父 Agent ID', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'artifacts/attribution-desktop.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await detail.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'artifacts/attribution-mobile.png' });
  await detail.getByRole('button', { name: '证据请求 ui-launch-evidence', exact: true }).click();
  await expect(detail.locator('#detail-id')).toHaveText('ui-launch-evidence');
});

test('分类用途和识别来源可见，旧记录缺字段仍兼容', async ({ page }) => {
  await page.goto('/'); await page.getByLabel('每 3 秒刷新').uncheck();
  const detail = page.getByRole('dialog');
  for (const item of [
    { purpose: 'auto_permission_classifier', profile: 'cc293-auto-mode-xml-s1', requestClass: 'auxiliary', querySource: 'auto_mode', label: '自动权限分类' },
    { purpose: 'session_title', profile: 'cc293-session-title-v1', requestClass: 'auxiliary', querySource: 'generate_session_title', label: '会话标题生成' },
    { purpose: 'compaction', profile: 'cc293-compact-full-v1', requestClass: 'compaction', querySource: 'compact', label: '会话压缩' },
  ]) {
    await page.route('**/api/logs/ui-compact', async route => {
      const response = await route.fetch(), value = await response.json();
      value.request.requestClass = item.requestClass;
      value.context = { ...value.context, inputFormat: 'claude_code', requestClass: item.requestClass, querySource: item.querySource, classification: { purpose: item.purpose, source: 'native_profile', profile: item.profile } };
      await route.fulfill({ response, json: value });
    });
    await page.getByTitle('ui-compact', { exact: true }).click();
    await expect(detail.getByText(item.label, { exact: true })).toBeVisible();
    await expect(detail.getByText('固定 293 原生构造证据', { exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await page.unroute('**/api/logs/ui-compact');
  }
  await page.route('**/api/logs/ui-main', async route => {
    const response = await route.fetch(), value = await response.json();
    delete value.context.inputFormat; delete value.context.classification; delete value.agentAssociation;
    await route.fulfill({ response, json: value });
  });
  await page.getByTitle('ui-main', { exact: true }).click();
  await expect(detail.getByText('旧记录未注明', { exact: true })).toBeVisible();
});

test('前置模型选择、最后写出来源及验证器失效状态只读可见', async ({ page }) => {
  let failed = false, posts = 0;
  await page.route('**/api/requests', async route => { posts++; await route.continue(); });
  await page.route('**/api/health', async route => {
    const response = await route.fetch(), value = await response.json();
    await route.fulfill({ response, json: { ...value, tlsCapture: 'verify', nativeFinalCapture: true, tlsVerifier: { profile: 'claude-code-2.1.293', state: failed ? 'failed' : 'ready' } } });
  });
  await page.route('**/api/logs/ui-main', async route => {
    const response = await route.fetch(), value = await response.json();
    value.request.model = 'ui-effective-model';
    value.context.modelSelection = { requested: 'ui-requested-model', effective: 'ui-effective-model', source: 'startup_override' };
    const final = value.captures.find((capture: { stage: string }) => capture.stage === 'wire_final');
    Object.assign(final, { source: 'native_tls_verifier', representation: 'http_entity_from_final_tls_write', status: 'complete', observedBytes: 2, storedBytes: 2, text: '{}', note: '测试显示夹具：最后 TLS 本地写出，不是上游实收证明' });
    await route.fulfill({ response, json: value });
  });
  await page.goto('/'); await page.getByLabel('每 3 秒刷新').uncheck();
  await expect(page.locator('#capture-hint')).toHaveText('最终 TLS 写出验证已开启（固定画像）');
  await page.getByRole('button', { name: 'ui-main', exact: true }).click();
  const detail = page.getByRole('dialog');
  await expect(detail.getByText('ui-requested-model', { exact: true })).toBeVisible();
  await expect(detail.getByText('本机启动配置', { exact: true })).toBeVisible();
  await detail.getByRole('tab', { name: '原始数据', exact: true }).click();
  await detail.getByRole('button', { name: /最终出站采样/ }).click();
  await expect(detail.locator('.capture-meta')).toContainText('native_tls_verifier');
  await expect(detail.locator('.section-note')).toContainText('不是上游实收证明');
  await page.keyboard.press('Escape'); failed = true; await page.reload();
  await expect(page.locator('#capture-hint')).toHaveText('最终 TLS 验证器不可用');
  await expect(page.locator('#health-warning')).toContainText('TLS 辅助程序失败');
  expect(posts).toBe(0);
});
