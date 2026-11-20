<script setup lang="ts">
import { ref } from 'vue';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input, InputGroup } from '@/components/ui/input';
import { Segmented, type SegmentedOption } from '@/components/ui/segmented';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { NumberInput, Pagination } from '@/components/ui/controls';
import { PageHeader } from '@/components/ui/page-header';
import { OverviewCard, OverviewGrid } from '@/components/ui/overview';
import { IconTile } from '@/components/ui/icon-tile';
import { Toolbar } from '@/components/ui/toolbar';
import { EntityAction, EntityBlock, EntityCard } from '@/components/ui/entity-card';
import { TableCard } from '@/components/ui/table-card';
import { FloatingSaveBar } from '@/components/ui/save-bar';
import { ModalDialog } from '@/components/ui/modal';
import { NoticeStrip } from '@/components/ui/notice-strip';
import { Activity, AlertCircle, Box, Calendar, Check, Clock, Filter, Globe, Info, KeyRound, Pencil, Plus, RefreshCw, Search, Server, Settings2, ShieldCheck, SlidersHorizontal, Trash2, Users, Zap } from '@/components/ui/icon';

/** 组合组件演示：数据取自设计稿 accounts / proxies / environments / settings 画面，供 verify_ui_kit.py 逐项比对。 */
const environmentFilter = ref('all');
const environmentOptions: SegmentedOption[] = [
  { value: 'all', label: '全部环境', count: 4 }, { value: 'ready', label: '就绪', count: 2 },
  { value: 'attention', label: '需要关注', count: 1 }, { value: 'stopped', label: '已停止', count: 1 },
];
const environments = [
  { name: '演示环境 A', account: '网关账号 #11', status: 'success', statusText: '就绪', warm: '热进程就绪', note: '293 空闲暖进程 1 / 存活 1 · 空闲 PID 27' },
  { name: '演示环境 3', account: '网关账号 #13', status: 'secondary', statusText: '已停止', warm: '环境已停止', note: '启动后自动预热 293 进程' },
] as const;
const proxies = [
  { name: '线路 1', url: 'http://proxy1.example.test:8080', ip: '203.0.113.1', region: 'SG 新加坡', latency: '42', expiry: '剩余 4 天 23 小时', expiryAt: '2026/11/24 19:36' },
  { name: '线路 2', url: 'http://proxy2.example.test:8080', ip: '203.0.113.2', region: 'JP 东京', latency: '88', expiry: '剩余 28 天', expiryAt: '2026/12/17 10:00' },
  { name: '线路 3', url: 'http://proxy3.example.test:8080', ip: '203.0.113.3', region: 'US 洛杉矶', latency: '186', expiry: '剩余 61 天', expiryAt: '2027/01/19 08:00' },
] as const;
const page = ref(1);
const pageSize = ref(20);
const pending = ref(1);
const admissionWait = ref<number | string>(99);
const modalOpen = ref(false);
const modalTab = ref('configuration');
const sideOpen = ref(false);
const logMode = ref<'info' | 'debug'>('info');
const quick = ref('all');
const quickOptions: SegmentedOption[] = [{ value: 'all', label: '全部', count: 53 }, { value: 'errors', label: '错误', count: 7 }, { value: 'processing', label: '处理中', count: 2 }];
const modalTabs: SegmentedOption[] = [
  { value: 'overview', label: '概览' }, { value: 'configuration', label: '配置' },
  { value: 'scheduling', label: '调度', count: 4 }, { value: 'diagnostics', label: '环境与诊断' },
];
</script>

<template>
  <section class="preview-card" data-testid="kit-composites">
    <div class="preview-section-title"><h2>组合组件</h2><span>页头 · 概览卡 · 工具栏 · 实体卡 · 数据表卡片 · 标签旁徽标 · 浮动保存栏</span></div>

    <PageHeader title="账号管理" description="状态、用量和调度集中展示，常用操作直接可达。" data-testid="page-header">
      <template #actions>
        <Button variant="outline"><KeyRound />授权登录</Button>
        <Button><Plus />添加账号</Button>
      </template>
    </PageHeader>

    <OverviewGrid class="composite-gap" data-testid="overview-grid">
      <OverviewCard label="代理" value="21" caption="条线路" data-testid="overview-card"><template #icon><Globe /></template></OverviewCard>
      <OverviewCard label="可用" value="19" unit="/ 21" caption="出口信息来自最近一次检测" tone="success" data-testid="overview-card-unit"><template #icon><Check /></template></OverviewCard>
      <OverviewCard label="被使用" value="6" caption="条线路有账号绑定" tone="info"><template #icon><Users /></template></OverviewCard>
      <OverviewCard label="7 天内到期" value="3" caption="另有 1 条已过期" tone="warning"><template #icon><Calendar /></template></OverviewCard>
    </OverviewGrid>

    <OverviewGrid class="composite-gap">
      <OverviewCard label="全部记录" value="53" caption="保留 7 天"><template #icon><Activity /></template></OverviewCard>
      <OverviewCard label="错误" value="7" caption="六类错误集合" tone="danger"><template #icon><AlertCircle /></template></OverviewCard>
      <OverviewCard label="处理中" value="2" caption="按当前筛选统计" tone="info"><template #icon><Clock /></template></OverviewCard>
      <OverviewCard interactive label="后续请求日志" :value="logMode === 'info' ? 'info · 摘要' : 'debug · 脱敏内容'" caption="仅影响后续请求 · 点击切换" tone="warning" data-testid="overview-card-interactive" @click="logMode = logMode === 'info' ? 'debug' : 'info'"><template #icon><SlidersHorizontal /></template></OverviewCard>
    </OverviewGrid>

    <TableCard class="composite-gap" data-testid="table-card-bare">
      <template #toolbar>
        <Toolbar>
          <Segmented v-model="quick" :options="quickOptions" label="请求快捷筛选" />
          <template #end>
            <InputGroup class="composite-search"><template #prefix><Search /></template><Input placeholder="输入完整请求 ID / 响应关联 ID / 上游请求 ID" /></InputGroup>
            <Button variant="outline"><Filter />筛选</Button>
            <Button><Search />查询</Button>
            <Button variant="outline" size="icon" aria-label="刷新"><RefreshCw /></Button>
          </template>
        </Toolbar>
      </template>
    </TableCard>

    <Toolbar class="composite-gap" data-testid="toolbar">
      <Segmented v-model="environmentFilter" :options="environmentOptions" label="环境状态筛选" />
      <span class="composite-note">显示 4 / 4 个环境</span>
      <template #end><InputGroup class="composite-search"><template #prefix><Search /></template><Input placeholder="搜索账号名称或环境 ID" /></InputGroup></template>
    </Toolbar>

    <div class="composite-entities composite-gap">
      <EntityCard v-for="(item, index) in environments" :key="item.name" :title="item.name" :data-testid="index === 0 ? 'entity-card' : undefined">
        <template #media><IconTile tone="cc" size="lg"><Box /></IconTile></template>
        <template #title-extra><Badge variant="cc">Claude Code</Badge></template>
        <template #subtitle>{{ item.account }} · <Server :size="14" />节点未观测</template>
        <template #status><Badge :variant="item.status" dot>{{ item.statusText }}</Badge></template>
        <EntityBlock :data-testid="index === 0 ? 'entity-block' : undefined"><b class="composite-block-title">{{ item.warm }}</b><p class="composite-block-note">{{ item.note }}</p></EntityBlock>
        <template #actions>
          <EntityAction tone="primary" :data-testid="index === 0 ? 'entity-action-primary' : undefined"><Box />环境详情</EntityAction>
          <EntityAction :data-testid="index === 0 ? 'entity-action' : undefined"><Settings2 />资源与采集</EntityAction>
          <EntityAction><Zap />请求内核</EntityAction>
          <EntityAction><ShieldCheck />维护</EntityAction>
        </template>
      </EntityCard>
    </div>

    <TableCard title="代理线路" count="21 / 21 条" class="composite-gap" data-testid="table-card">
      <template #toolbar>
        <InputGroup class="composite-search"><template #prefix><Search /></template><Input placeholder="名称、地址、出口 IP 或地区" /></InputGroup>
        <Button variant="outline"><Activity />批量检测</Button>
      </template>
      <Table class="composite-table">
        <TableHeader><TableRow><TableHead>代理线路</TableHead><TableHead>出口 IP / 地区</TableHead><TableHead>检测延迟</TableHead><TableHead>到期时间</TableHead><TableHead class="fui-table-actions">操作</TableHead></TableRow></TableHeader>
        <TableBody>
          <TableRow v-for="row in proxies" :key="row.name">
            <TableCell><div class="composite-identity"><IconTile size="sm" :data-testid="row.name === '线路 1' ? 'icon-tile-sm' : undefined"><Globe /></IconTile><div><b>{{ row.name }}</b><span class="fui-table-sub">{{ row.url }}</span></div></div></TableCell>
            <TableCell>{{ row.ip }}<span class="fui-table-sub">{{ row.region }}</span></TableCell>
            <TableCell>{{ row.latency }} ms</TableCell>
            <TableCell>{{ row.expiry }}<span class="fui-table-sub">{{ row.expiryAt }}</span></TableCell>
            <TableCell class="fui-table-actions" :data-testid="row.name === '线路 1' ? 'table-actions' : undefined"><div class="composite-ops"><Button variant="outline" size="sm"><Activity />检测</Button><Button variant="outline" size="sm"><Pencil />编辑</Button><Button variant="destructive-ghost" size="sm"><Trash2 />删除</Button></div></TableCell>
          </TableRow>
        </TableBody>
      </Table>
      <template #footer><Pagination v-model:page="page" v-model:page-size="pageSize" :total="21" label="代理线路分页" /></template>
    </TableCard>

    <div class="composite-gap composite-notices">
      <NoticeStrip tone="success" data-testid="notice-strip"><Check />网关凭据正常 · 最近同步 3 分钟前</NoticeStrip>
      <NoticeStrip data-testid="notice-strip-neutral"><Info />维护期间新工作暂缓，在途工作自然结束后继续。</NoticeStrip>
      <NoticeStrip tone="danger">invalid_grant：账号异常，需要重新授权或人工核实。长说明在窄宽下换行，提示条随内容增高。<template #end><Badge variant="outline">需处理</Badge></template></NoticeStrip>
    </div>

    <div class="composite-gap">
      <Button variant="outline" @click="modalOpen = true">打开居中弹窗示例</Button>
      <ModalDialog v-model:open="modalOpen" title="正式账号 1" description="design1@example.test" :width="820" data-testid="modal">
        <template #media><IconTile size="lg">正</IconTile></template>
        <template #title-extra><Badge variant="cc">Claude Code</Badge><Badge>Max</Badge></template>
        <template #nav><Segmented v-model="modalTab" :options="modalTabs" label="账号工作区" data-testid="modal-nav" /></template>
        <div class="composite-modal-section"><b>转发方式</b><p>原生运行时按账号绑定的内核版本转发，修改后在空闲时生效。</p></div>
        <div class="composite-modal-section"><b>调度优先级</b><p>数值越大越优先，0–100。</p></div>
        <template #footer>
          <span class="composite-note">修改后统一保存</span>
          <Button variant="outline" class="composite-push" @click="modalOpen = false">取消</Button>
          <Button @click="modalOpen = false">保存修改</Button>
        </template>
      </ModalDialog>
      <Button variant="outline" @click="sideOpen = true">打开靠右抽屉示例</Button>
      <ModalDialog v-model:open="sideOpen" title="请求详情" placement="side" :width="1020" data-testid="modal-side">
        <template #description><code>11111111-1111-4111-8111-111111111111</code></template>
        <div class="composite-modal-section"><b>上游尝试</b><p>按实际提交顺序展示，每次尝试保留自己的账号与结果。</p></div>
      </ModalDialog>
    </div>

    <div class="composite-fields composite-gap" data-testid="label-extra-field">
      <NumberInput v-model="admissionWait" label="准入等待上限（秒）" :min="1" :max="120"><template #label-extra><Badge v-if="admissionWait !== 120" variant="warning" data-testid="label-extra-badge">已修改</Badge></template></NumberInput>
    </div>

    <FloatingSaveBar :count="pending" hint="修改将统一应用到网关" clean-label="配置已同步" data-testid="save-bar">
      <template #actions>
        <Button variant="outline" :disabled="!pending" @click="pending = 0"><RefreshCw />撤销修改</Button>
        <Button :disabled="!pending" @click="pending = 0">保存配置</Button>
      </template>
    </FloatingSaveBar>
  </section>
</template>

<style scoped>
.composite-gap { margin-bottom: calc(var(--ui-space-unit) * 4.5); }
.composite-notices { display: grid; gap: calc(var(--ui-space-unit) * 2.5); max-width: 560px; }
.composite-note { color: var(--ui-color-text-3); font-size: var(--ui-font-size-sm); font-weight: 600; }
.composite-identity { display: flex; align-items: center; gap: calc(var(--ui-space-unit) * 2.5); min-width: 0; }
.composite-search { width: 280px; }
.composite-entities { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--ui-space-unit) * 4); }
.composite-block-title { color: var(--ui-color-success-text); font-size: var(--ui-font-size-md); font-weight: 720; }
.composite-block-note { margin: 2px 0 0; color: var(--ui-color-text-2); font-size: var(--ui-font-size-sm); font-weight: 550; }
/* 固定宽度让窄视口出现横向滚动，演示操作列固定。 */
.composite-table { min-width: 880px; }
.composite-modal-section b { font-size: var(--ui-font-size-title); font-weight: 760; }
.composite-modal-section p { margin: 2px 0 0; color: var(--ui-color-text-3); font-size: var(--ui-font-size-sm); }
.composite-push { margin-left: auto; }
.composite-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--ui-space-unit) * 4.5) calc(var(--ui-space-unit) * 5); max-width: 860px; }
.composite-ops { display: flex; justify-content: flex-end; gap: calc(var(--ui-space-unit) * 1); }
@media (max-width: 760px) { .composite-entities, .composite-fields { grid-template-columns: minmax(0, 1fr); } .composite-search { width: 100%; } }
</style>
