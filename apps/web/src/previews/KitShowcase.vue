<script setup lang="ts">
import { ref } from 'vue';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input, InputGroup } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Segmented, type SegmentedOption } from '@/components/ui/segmented';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { RadioCardGroup, type RadioCardOption } from '@/components/ui/radio-card';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Empty } from '@/components/ui/empty';
import { Skeleton } from '@/components/ui/skeleton';
import { Pagination } from '@/components/ui/controls';
import { Activity, AlertCircle, Globe, Pencil, Plus, RefreshCw, Search, Server, Trash2 } from '@/components/ui/icon';

/** 组件库逐项演示：静态呈现默认、选中、禁用、加载态，悬停与焦点保持可交互，供 verify_ui_kit.py 读取计算样式。 */
const variants = [
  { variant: 'default', label: '主要' }, { variant: 'outline', label: '次要' }, { variant: 'soft', label: '柔和' },
  { variant: 'destructive', label: '危险' }, { variant: 'ghost', label: '文字' }, { variant: 'destructive-ghost', label: '文字危险' },
  { variant: 'link', label: '链接' },
] as const;
const filter = ref('all');
const filterOptions: SegmentedOption[] = [
  { value: 'all', label: '全部', count: 128 }, { value: 'errors', label: '错误', count: 6, icon: AlertCircle },
  { value: 'processing', label: '处理中', count: 2 }, { value: 'archived', label: '已归档', disabled: true },
];
const tones = [
  { variant: 'success', label: '运行中' }, { variant: 'warning', label: '待检查' }, { variant: 'destructive', label: '已失效' },
  { variant: 'info', label: '同步中' }, { variant: 'secondary', label: '已停用' }, { variant: 'default', label: '偏好' },
  { variant: 'cc', label: 'Claude Code' }, { variant: 'agy', label: '反重力' }, { variant: 'outline', label: '描边' },
] as const;
const accepting = ref(true);
const paused = ref(false);
const agreed = ref(true);
const partial = ref<boolean | 'indeterminate'>('indeterminate');
const unchecked = ref(false);
const forwarding = ref('native');
const forwardingOptions: RadioCardOption[] = [
  { value: 'native', label: '原生运行时', description: '按账号绑定的内核版本转发' },
  { value: 'legacy', label: '原有转发', description: '沿用旧版请求改写' },
  { value: 'mock', label: '模拟响应', description: '暂不可用', disabled: true },
];
// 取自设计稿代理画面（doc/design/console-v2/mock.html#proxies），用于逐项对照表格。
const rows = [
  { name: '线路 1', url: 'http://proxy1.example.test:8080', ip: '203.0.113.1', region: 'SG 新加坡', latency: '42', status: 'success', statusText: '可用', expiry: '剩余 4 天 23 小时', expiryAt: '2026/11/24 19:36', usage: '1 个使用 · 0 个活跃', accounts: '正式账号 1' },
  { name: '线路 2', url: 'http://proxy2.example.test:8080', ip: '203.0.113.2', region: 'JP 东京', latency: '88', status: 'success', statusText: '可用', expiry: '剩余 28 天', expiryAt: '2026/12/17 10:00', usage: '2 个使用 · 1 个活跃', accounts: '反重力账号 4 等' },
  { name: '线路 3', url: 'http://proxy3.example.test:8080', ip: '203.0.113.3', region: 'US 洛杉矶', latency: '186', status: 'warning', statusText: '较慢', expiry: '剩余 61 天', expiryAt: '2027/01/19 08:00', usage: '1 个使用 · 1 个活跃', accounts: '正式账号 3' },
  { name: '线路 4', url: 'http://proxy4.example.test:8080', ip: '203.0.113.4', region: 'SG 新加坡', latency: '—', status: 'destructive', statusText: '不可用', expiry: '已过期 2 天', expiryAt: '2026/11/17 09:00', usage: '0 个使用', accounts: '' },
  { name: '线路 5', url: 'http://proxy5.example.test:8080', ip: '203.0.113.5', region: 'HK 香港', latency: '51', status: 'success', statusText: '可用', expiry: '剩余 6 天', expiryAt: '2026/11/26 12:00', usage: '0 个使用', accounts: '' },
  { name: '线路 6', url: 'http://proxy6.example.test:8080', ip: '203.0.113.6', region: 'DE 法兰克福', latency: '214', status: 'success', statusText: '可用', expiry: '长期有效', expiryAt: '—', usage: '0 个使用', accounts: '' },
] as const;

/** 延迟按数值着色：超过 150ms 为警告色，无值为弱化色。@param value 毫秒文本。@return 样式类。 */
function latencyTone(value: string): string {
  return value === '—' ? 'is-empty' : Number(value) > 150 ? 'is-slow' : 'is-fast';
}

/** 到期标签色：已过期为危险，7 天内为警告，其余中性。@param text 到期描述。@return Badge 变体。 */
function expiryTone(text: string): 'destructive' | 'warning' | 'secondary' {
  return text.startsWith('已过期') ? 'destructive' : /剩余 [1-6] 天/.test(text) ? 'warning' : 'secondary';
}
const page = ref(1);
const pageSize = ref(20);
const dialogOpen = ref(false);
const dialogMode = ref('native');
</script>

<template>
  <section class="preview-card" data-testid="kit-buttons">
    <div class="preview-section-title"><h2>按钮</h2><span>主要 / 次要 / 柔和 / 危险 / 文字 · 38 与 32 两档</span></div>
    <div class="kit-row">
      <Button v-for="item in variants" :key="item.variant" :variant="item.variant" :data-testid="`button-${item.variant}`">{{ item.label }}</Button>
    </div>
    <div class="kit-row">
      <Button v-for="item in variants" :key="item.variant" :variant="item.variant" size="sm" :data-testid="`button-sm-${item.variant}`">{{ item.label }}</Button>
    </div>
    <div class="kit-row">
      <Button data-testid="button-icon-label"><Plus />添加账号</Button>
      <Button variant="outline" size="icon" aria-label="刷新" data-testid="button-icon"><RefreshCw /></Button>
      <Button variant="ghost" size="icon-sm" aria-label="编辑"><Pencil /></Button>
      <Button variant="destructive-ghost" size="icon-sm" aria-label="删除"><Trash2 /></Button>
      <Button size="lg">大号按钮</Button>
      <Button disabled data-testid="button-disabled">禁用</Button>
      <Button variant="outline" disabled aria-busy="true" data-testid="button-loading"><RefreshCw class="fui-spinning" />处理中…</Button>
    </div>
  </section>

  <section class="preview-card" data-testid="kit-inputs">
    <div class="preview-section-title"><h2>输入</h2><span>静止填充 · 聚焦外圈 · 前后缀</span></div>
    <div class="preview-grid">
      <label class="kit-field"><span class="fui-label">账号名称</span><Input placeholder="例如 主用演示账号" data-testid="input-default" /><span class="fui-field-help" data-testid="field-help">只用于控制台展示，不影响上游身份。</span></label>
      <label class="kit-field"><span class="fui-label">只读字段</span><Input model-value="acct_7f2c91" readonly data-testid="input-readonly" /></label>
      <label class="kit-field"><span class="fui-label">禁用字段</span><Input model-value="不可编辑" disabled /></label>
      <label class="kit-field"><span class="fui-label">校验失败</span><Input model-value="abc" aria-invalid="true" data-testid="input-invalid" /></label>
      <label class="kit-field"><span class="fui-label">带前后缀</span><InputGroup data-testid="input-group"><template #prefix><Search /></template><Input placeholder="搜索代理名称" /><template #suffix><span>⌘K</span></template></InputGroup></label>
      <label class="kit-field"><span class="fui-label">备注</span><Textarea placeholder="每行一条" /></label>
    </div>
  </section>

  <section class="preview-card" data-testid="kit-segmented">
    <div class="preview-section-title"><h2>分段与标签</h2><span>带计数 · 圆点状态</span></div>
    <div class="kit-row">
      <Segmented v-model="filter" :options="filterOptions" label="请求结果筛选" />
      <span class="preview-help" data-testid="segmented-result">当前：{{ filter }}</span>
    </div>
    <div class="kit-row">
      <Badge v-for="item in tones" :key="item.variant" :variant="item.variant" dot :data-testid="`badge-${item.variant}`">{{ item.label }}</Badge>
    </div>
    <div class="kit-row">
      <Badge v-for="item in tones" :key="item.variant" :variant="item.variant">{{ item.label }}</Badge>
    </div>
  </section>

  <section class="preview-card" data-testid="kit-toggles">
    <div class="preview-section-title"><h2>开关、复选与单选卡</h2><span>选中 / 未选 / 禁用</span></div>
    <div class="kit-row">
      <span class="kit-inline" data-testid="switch-label">接收请求<Switch v-model="accepting" label="接收请求" data-testid="switch-on" /></span>
      <span class="kit-inline"><Switch v-model="paused" label="暂停接单" data-testid="switch-off" />暂停接单</span>
      <span class="kit-inline"><Switch :model-value="true" label="禁用开关" disabled />禁用</span>
    </div>
    <div class="kit-row">
      <Checkbox v-model="agreed" data-testid="checkbox-checked">保存后同步网关账号</Checkbox>
      <Checkbox v-model="partial">部分选中</Checkbox>
      <Checkbox v-model="unchecked">未选中</Checkbox>
      <Checkbox :model-value="false" disabled>禁用复选</Checkbox>
    </div>
    <RadioCardGroup v-model="forwarding" :options="forwardingOptions" label="转发方式" data-testid="radio-cards" />
  </section>

  <section class="preview-card" data-testid="kit-data">
    <div class="preview-section-title"><h2>卡片、表格与分页</h2><span>无描边卡片 · 圆角表头 · 斑马行</span></div>
    <Card class="kit-card" data-testid="card">
      <CardHeader class="kit-card-head">
        <CardTitle>代理线路<small class="kit-count" data-testid="card-count">21 / 21 条</small></CardTitle>
        <InputGroup class="kit-search"><template #prefix><Search /></template><Input placeholder="名称、地址、出口 IP 或地区" /></InputGroup>
        <Button variant="outline"><Activity />批量检测</Button>
      </CardHeader>
      <CardContent>
        <Table class="kit-proxy-table" data-testid="table">
          <colgroup><col style="width:20%"><col style="width:13%"><col style="width:9%"><col style="width:9%"><col style="width:14%"><col style="width:13%"><col style="width:22%"></colgroup>
          <TableHeader><TableRow><TableHead>代理线路</TableHead><TableHead>出口 IP / 地区</TableHead><TableHead>检测延迟</TableHead><TableHead>连接状态</TableHead><TableHead>到期时间</TableHead><TableHead>账号使用情况</TableHead><TableHead class="text-right">操作</TableHead></TableRow></TableHeader>
          <TableBody>
            <TableRow v-for="row in rows" :key="row.name">
              <TableCell><div class="kit-route"><span class="kit-tile"><Globe :size="14" /></span><div><b>{{ row.name }}</b><span class="fui-table-sub kit-mono">{{ row.url }}</span></div></div></TableCell>
              <TableCell><span class="kit-mono">{{ row.ip }}</span><span class="fui-table-sub">{{ row.region }}</span></TableCell>
              <TableCell><b class="kit-latency kit-mono" :class="latencyTone(row.latency)" :data-testid="row.name === '线路 1' ? 'latency' : undefined">{{ row.latency }}</b> <span class="kit-unit" :data-testid="row.name === '线路 1' ? 'latency-unit' : undefined">ms</span></TableCell>
              <TableCell><Badge :variant="row.status" dot>{{ row.statusText }}</Badge></TableCell>
              <TableCell><Badge :variant="expiryTone(row.expiry)" :data-testid="row.name === '线路 1' ? 'expiry-warning' : undefined">{{ row.expiry }}</Badge><span class="fui-table-sub kit-num">{{ row.expiryAt }}</span></TableCell>
              <TableCell>{{ row.usage }}<span class="fui-table-sub">{{ row.accounts || '暂无账号' }}</span></TableCell>
              <TableCell><div class="kit-ops"><Button variant="outline" size="sm" class="kit-op"><Activity />检测</Button><Button variant="outline" size="sm"><Pencil />编辑</Button><Button variant="destructive-ghost" size="sm"><Trash2 />删除</Button></div></TableCell>
            </TableRow>
          </TableBody>
        </Table>
        <Pagination v-model:page="page" v-model:page-size="pageSize" :total="86" label="代理分页" />
      </CardContent>
    </Card>
    <div class="preview-grid">
      <div class="kit-skeleton" data-testid="skeleton"><Skeleton class="kit-skeleton-title" /><Skeleton /><Skeleton class="kit-skeleton-short" /></div>
      <Empty title="还没有节点" description="添加一台服务器后，可在此查看组件状态与账号归属。" data-testid="empty">
        <template #icon><Server /></template>
        <template #actions><Button size="sm"><Plus />添加节点</Button></template>
      </Empty>
    </div>
  </section>

  <section class="preview-card" data-testid="kit-dialog">
    <div class="preview-section-title"><h2>弹窗</h2><span>18px 圆角 · 遮罩 · Esc 关闭</span></div>
    <Button variant="outline" @click="dialogOpen = true">打开弹窗示例</Button>
    <Dialog v-model:open="dialogOpen">
      <DialogContent class="kit-dialog">
        <DialogHeader><DialogTitle>编辑账号</DialogTitle><DialogDescription>修改转发方式，保存后对后续请求生效。</DialogDescription></DialogHeader>
        <RadioCardGroup v-model="dialogMode" :options="forwardingOptions" label="弹窗内转发方式" />
        <DialogFooter><Button variant="outline" @click="dialogOpen = false">取消</Button><Button @click="dialogOpen = false">保存</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  </section>
</template>

<style scoped>
.kit-row { display: flex; flex-wrap: wrap; align-items: center; gap: calc(var(--ui-space-unit) * 2.5); margin-bottom: calc(var(--ui-space-unit) * 4); }
.kit-field { display: grid; gap: calc(var(--ui-space-unit) * 1.75); min-width: 0; }
.kit-inline { display: inline-flex; align-items: center; gap: calc(var(--ui-space-unit) * 2.5); font-size: var(--ui-font-size-meta); font-weight: 600; color: var(--ui-color-text-2); }
.kit-card { margin-bottom: calc(var(--ui-space-unit) * 5); }
.kit-card-head { display: flex; align-items: center; gap: calc(var(--ui-space-unit) * 2.5); }
.kit-card-head > [data-slot=card-title] { display: flex; align-items: baseline; gap: calc(var(--ui-space-unit) * 2); margin-right: auto; }
.kit-count { color: var(--ui-color-text-4); font: 650 var(--ui-font-size-sm) var(--ui-font-family-mono); }
.kit-search { width: 300px; }
.kit-card :deep(.kit-proxy-table) { table-layout: fixed; }
.kit-card :deep(.kit-proxy-table td) { overflow: hidden; text-overflow: ellipsis; }
.kit-route { display: flex; align-items: center; gap: calc(var(--ui-space-unit) * 2.5); }
.kit-route > div { min-width: 0; }
.kit-route b { font-weight: 720; }
.kit-tile { display: grid; place-items: center; flex: none; width: 32px; height: 32px; border-radius: calc(var(--ui-radius-block) - 3px); background: var(--ui-color-primary-container); color: var(--ui-color-primary-text); }
.kit-mono { font-family: var(--ui-font-family-mono); font-variant-numeric: tabular-nums; }
.kit-num { font-variant-numeric: tabular-nums; }
.kit-latency { font-size: var(--ui-font-size-card); }
.kit-latency.is-fast { color: var(--ui-color-success-text); }
.kit-latency.is-slow { color: var(--ui-color-warning-text); }
.kit-latency.is-empty { color: var(--ui-color-text-4); }
.kit-unit { color: var(--ui-color-text-4); }
.kit-ops { display: flex; justify-content: flex-end; gap: calc(var(--ui-space-unit) * 1); }
.kit-card :deep(.fui-pagination) { margin-top: calc(var(--ui-space-unit) * 3.5); }
.kit-skeleton { display: grid; align-content: start; gap: calc(var(--ui-space-unit) * 2.5); padding: calc(var(--ui-space-unit) * 4); border-radius: var(--ui-radius-block); background: var(--ui-color-surface); }
.kit-skeleton-title { width: 40%; height: 18px; }
.kit-skeleton-short { width: 65%; }
.kit-dialog { width: min(640px, calc(100vw - 32px)); max-width: none; }
</style>
