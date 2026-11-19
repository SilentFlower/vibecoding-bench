<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { FeedbackHost, OperationFeedback } from '../components/ui/feedback';
import { useToast } from '../composables/useToast';
import { useConfirmation } from '../composables/useConfirmation';
import { NumberInput, ChoiceSelect, InfoTooltip, SearchInput } from '@/components/ui/controls';
import type { ChoiceOption } from '@/components/ui/controls';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Segmented, type SegmentedOption } from '@/components/ui/segmented';
import { Switch } from '@/components/ui/switch';
import { Check, Save, RotateCcw } from '@/components/ui/icon';
import { DEFAULT_THEME_SEED, THEME_PRESETS, applyTheme, createTheme, readStoredTheme, writeStoredTheme, type ThemeSeed } from '@/theme';
import KitShowcase from './KitShowcase.vue';

const { show: notify } = useToast();
const { ask } = useConfirmation();
const demoResult = ref<'idle' | 'success'>('idle');
/** 本地演示确认，结果只进入示例通知。@return 完成。 */
async function confirmExample(): Promise<void> { if (await ask({ title: '确认操作', message: '这是本地组件演示。确认后显示成功反馈。', confirmLabel: '确认示例' })) notify('示例操作已完成', 'success'); }
const concurrency = ref<number | string>(3);
const limit = ref<number | string>(90);
const precision = ref<number | string>(0.5);
const subscription = ref('max');
const auth = ref('oauth');
const query = ref('');
const searched = ref('');
const submitted = ref('尚未保存');
const dialog = ref<HTMLDialogElement>();
const dialogChoice = ref('oauth');
const options: ChoiceOption[] = [
  { value: '', label: '未设置' }, { value: 'max', label: 'Max' },
  { value: 'pro', label: 'Pro' }, { value: 'ultra', label: 'Ultra' },
  { value: 'enterprise', label: 'Enterprise（暂不可用）', disabled: true },
];
const authOptions: ChoiceOption[] = [{ value: 'oauth', label: 'OAuth' }, { value: 'setup_token', label: 'Setup Token' }];

/** 仅回显本地表单结果，演示原始选项值和数字清空语义。@param event 提交事件。@return 无。 */
function save(event: Event): void {
  const form = event.target as HTMLFormElement;
  submitted.value = JSON.stringify(Object.fromEntries(new FormData(form)), null, 2);
}

// 主题草稿直接作用于整页，便于逐项核对；保存才写入浏览器存储，刷新后由 initTheme 恢复。
const seed = ref<ThemeSeed>({ ...(readStoredTheme() ?? DEFAULT_THEME_SEED) });
const themeStatus = ref('');
const surfaceOptions: SegmentedOption[] = [{ value: 'default', label: '默认' }, { value: 'soft', label: '柔光' }];
watch(seed, value => applyTheme(document.documentElement, createTheme(value)), { deep: true });

/** 读取颜色选择器的值作为自定义主色。@param event 输入事件。@return 无。 */
function pickPrimary(event: Event): void {
  seed.value.primary = (event.target as HTMLInputElement).value;
}

/** 切换表面材质。@param value 分段值。@return 无。 */
function pickSurface(value: string): void {
  seed.value.surface = value === 'soft' ? 'soft' : 'default';
}

/** 保存当前草稿到浏览器。@return 无。 */
function saveTheme(): void {
  themeStatus.value = writeStoredTheme(seed.value) ? '已保存，刷新后保持' : '浏览器存储不可用，未保存';
}

/** 清除保存值并回到第二版默认主题。@return 无。 */
function resetTheme(): void {
  writeStoredTheme(null);
  seed.value = { ...DEFAULT_THEME_SEED };
  themeStatus.value = '已恢复默认';
}

// 局部主题示例：只给该容器写变量，验证主题设置画板的隔离能力。
const localTheme = ref<HTMLElement>();
onMounted(() => { if (localTheme.value) applyTheme(localTheme.value, createTheme({ ...DEFAULT_THEME_SEED, primary: '#0f9f8f', radius: 4 })); });
const localFilter = ref('on');
const localOptions: SegmentedOption[] = [{ value: 'on', label: '启用', count: 3 }, { value: 'off', label: '停用', count: 1 }];
const localSwitch = ref(true);
</script>

<template>
  <main class="ui-preview">
    <header class="preview-heading"><span>flower2api / UI COMPONENTS</span><h1>让页面共享同一套细节</h1><p>第二版组件库与主题运行时 · 本地交互示例</p></header>

    <section class="preview-card preview-theme" data-testid="theme-toolbar" aria-label="主题">
      <div class="preview-section-title"><h2>主题</h2><span aria-live="polite" data-testid="theme-status">{{ themeStatus || '草稿实时作用于本页' }}</span></div>
      <div class="preview-presets">
        <button v-for="preset in THEME_PRESETS" :key="preset.id" type="button" class="preview-preset" :aria-pressed="seed.primary === preset.primary" :data-testid="`preset-${preset.id}`" @click="seed.primary = preset.primary">
          <i :style="{ background: preset.primary }" /><b>{{ preset.name }}</b><small>{{ preset.description }}</small><Check v-if="seed.primary === preset.primary" :size="12" />
        </button>
      </div>
      <div class="preview-theme-actions">
        <label class="preview-color">自定义主色<input type="color" :value="seed.primary" data-testid="custom-primary" @input="pickPrimary"></label>
        <Segmented :model-value="seed.surface" :options="surfaceOptions" label="表面材质" @update:model-value="pickSurface" />
        <span class="preview-spacer" />
        <Button variant="ghost" size="sm" data-testid="theme-reset" @click="resetTheme"><RotateCcw />恢复默认</Button>
        <Button size="sm" data-testid="theme-save" @click="saveTheme"><Save />保存主题</Button>
      </div>
    </section>

    <form class="preview-card" @submit.prevent="save">
      <div class="preview-section-title"><h2>表单控件</h2><span>38px 高度 · 聚焦外圈</span></div>
      <div class="preview-grid three">
        <NumberInput v-model="concurrency" label="并发上限" name="concurrency" :min="1" :max="10" required />
        <NumberInput v-model="limit" label="5 小时用量上限（%）" name="limit" :min="0" :max="100" required />
        <NumberInput v-model="precision" label="小数步长示例" name="precision" :min="0" :max="1" :step="0.1" />
      </div>
      <div class="preview-grid">
        <ChoiceSelect v-model="subscription" :options="options" label="订阅类型" name="subscription" />
        <ChoiceSelect v-model="auth" :options="authOptions" label="授权方式" name="auth" />
        <NumberInput :model-value="3" label="禁用数字输入" disabled />
        <ChoiceSelect model-value="oauth" :options="authOptions" label="禁用选择" disabled />
      </div>
      <div class="preview-footer"><p>输入范围与必填由原生表单校验；空选项保留空字符串。</p><Button type="submit">保存示例</Button></div>
      <pre data-testid="form-result">{{ submitted }}</pre>
    </form>

    <KitShowcase />

    <section class="preview-card">
      <div class="preview-section-title"><h2>搜索与完整信息</h2><span>聚焦容器 · 溢出可查看</span></div>
      <SearchInput v-model="query" label="会话搜索" placeholder="搜索脱敏摘要前缀" @search="searched = $event" />
      <p class="preview-help" data-testid="search-result">已搜索：{{ searched || '—' }}</p>
      <InfoTooltip label="查看用量统计" title="5 小时用量统计">
        <template #trigger><span class="preview-summary">128 请求 · 845K Token · 折算 $4.85 · 预计总费用 $15.16</span></template>
        <dl class="preview-tooltip-grid"><div><dt>请求数</dt><dd>128</dd></div><div><dt>Token</dt><dd>845,000</dd></div><div><dt>折算费用</dt><dd>$4.85</dd></div><div><dt>预计总费用</dt><dd>$15.16</dd></div></dl>
        <p class="preview-help">预计总费用按网关费用与官方用量比例估算。</p>
      </InfoTooltip>
    </section>
    <section class="preview-card"><div class="preview-section-title"><h2>浮层中的组件</h2><span>保持菜单与气泡的正确层级</span></div><p class="preview-help">同一组组件可放入编辑窗口，支持键盘关闭及焦点返回。</p><Button variant="outline" type="button" @click="dialog?.showModal()">打开窗口示例</Button></section>
    <section class="preview-card"><div class="preview-section-title"><h2>操作反馈</h2><span>通知、确认与固定位置结果</span></div><div class="preview-footer"><Button variant="outline" type="button" @click="notify('本地示例已保存','success')">成功通知</Button><Button variant="outline" type="button" @click="notify('示例操作失败，请核对输入后重试','error')">错误通知</Button><Button variant="outline" type="button" @click="confirmExample">确认弹窗</Button><OperationFeedback :status="demoResult" message="本地合成连接正常" @action="demoResult='success'" /></div></section>

    <section ref="localTheme" class="preview-card" data-testid="local-theme" aria-label="局部主题">
      <div class="preview-section-title"><h2>局部主题</h2><span>松石绿 · 圆角 4，只作用于本区域</span></div>
      <div class="preview-footer">
        <Button data-testid="local-button">局部主按钮</Button>
        <Segmented v-model="localFilter" :options="localOptions" label="局部分段" />
        <Badge variant="default" dot>局部标签</Badge>
        <Switch v-model="localSwitch" label="局部开关" />
      </div>
    </section>

    <FeedbackHost />
    <dialog ref="dialog" class="preview-dialog" aria-labelledby="preview-dialog-title">
      <header><h2 id="preview-dialog-title">授权登录 · 组件示例</h2><Button variant="ghost" size="sm" aria-label="关闭窗口" type="button" @click="dialog?.close()">关闭</Button></header>
      <div class="preview-dialog-body">
        <ChoiceSelect v-model="dialogChoice" :options="authOptions" label="窗口内授权方式" :portal-target="dialog" />
        <NumberInput v-model="concurrency" label="窗口内并发上限" :min="1" :max="10" />
        <InfoTooltip label="查看授权说明" title="授权方式" :portal-target="dialog"><template #trigger>查看授权说明</template><p>账号配置由任务或工程创建流程提供，当前为本地组件演示。</p></InfoTooltip>
      </div>
    </dialog>
  </main>
</template>

<style>
/* 演示页是独立入口，布局样式以 .ui-preview 为前缀全局生效，供多根的 KitShowcase 分节共用。 */
/* 正文基准取第二版设计稿的 13px / 1.55，迁移后的页面使用同一基准。 */
body:has(.ui-preview) { background: var(--ui-color-layout); font-size: var(--ui-font-size-md); line-height: 1.55; }
.ui-preview { max-width: 1240px; margin: 0 auto; padding: 52px 26px; font-family: var(--ui-font-family); font-size: var(--ui-font-size-md); color: var(--ui-color-text); }
.ui-preview .preview-heading { margin-bottom: 30px; }
.ui-preview .preview-heading>span { font-size: var(--ui-font-size-sm); font-weight: 700; color: var(--ui-color-primary-text); letter-spacing: 1.2px; }
.ui-preview .preview-heading h1 { margin: 12px 0 8px; font-size: var(--ui-font-size-page); font-weight: 800; letter-spacing: -.02em; }
.ui-preview .preview-heading p { color: var(--ui-color-text-3); font-weight: 550; }
.ui-preview .preview-card { margin-bottom: 20px; padding: 24px; border-radius: var(--ui-radius-card); background: var(--ui-color-surface); box-shadow: var(--ui-shadow-card); }
.ui-preview .preview-section-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 20px; }
.ui-preview .preview-section-title h2 { margin: 0; font-size: var(--ui-font-size-card); font-weight: 760; }
.ui-preview .preview-section-title>span { color: var(--ui-color-text-3); font-size: var(--ui-font-size-sm); font-weight: 550; }
.ui-preview .preview-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 20px 18px; margin-bottom: 20px; }
.ui-preview .preview-grid.three { grid-template-columns: repeat(3,minmax(0,1fr)); }
.ui-preview .preview-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px; padding-top: 18px; border-top: 1px solid var(--ui-color-line); }
.ui-preview .preview-footer p, .ui-preview .preview-help { margin: 0; color: var(--ui-color-text-3); font-size: var(--ui-font-size-sm); line-height: 1.8; }
.ui-preview .preview-help { margin: 12px 0; }
.ui-preview pre { margin-top: 18px; padding: 12px; border-radius: var(--ui-radius-control); background: var(--ui-color-fill-subtle); color: var(--ui-color-text-3); font-size: var(--ui-font-size-sm); white-space: pre-wrap; }
.ui-preview .preview-summary { display: block; max-width: min(320px,70vw); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ui-preview .preview-tooltip-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.ui-preview .preview-tooltip-grid dt { color: var(--ui-color-text-3); font-size: var(--ui-font-size-sm); }
.ui-preview .preview-tooltip-grid dd { margin: 3px 0 0; color: var(--ui-color-text); }
.ui-preview .preview-presets { display: grid; grid-template-columns: repeat(6,minmax(0,1fr)); gap: 8px; margin-bottom: 14px; }
.ui-preview .preview-preset { position: relative; display: flex; flex-direction: column; gap: 2px; padding: 7px 7px 8px; border: 0; border-radius: var(--ui-radius-block); background: var(--ui-color-fill-subtle); color: var(--ui-color-text); text-align: left; cursor: pointer; }
.ui-preview .preview-preset[aria-pressed=true] { background: var(--ui-color-surface); box-shadow: 0 0 0 1.5px var(--ui-color-primary), var(--ui-shadow-pop); }
.ui-preview .preview-preset:focus-visible { outline: 2px solid var(--ui-color-primary); outline-offset: 2px; }
.ui-preview .preview-preset i { display: block; height: 24px; margin-bottom: 5px; border-radius: var(--ui-radius-btn); }
.ui-preview .preview-preset b { font-size: var(--ui-font-size-sm); font-weight: 750; }
.ui-preview .preview-preset small { color: var(--ui-color-text-4); font-size: var(--ui-font-size-xs); font-weight: 600; }
.ui-preview .preview-preset svg { position: absolute; right: 8px; bottom: 10px; color: var(--ui-color-primary); }
.ui-preview .preview-theme-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.ui-preview .preview-color { display: inline-flex; align-items: center; gap: 8px; color: var(--ui-color-text-2); font-size: var(--ui-font-size-meta); font-weight: 650; }
.ui-preview .preview-color input { width: 38px; height: 30px; padding: 0; border: 0; border-radius: var(--ui-radius-btn); background: none; cursor: pointer; }
.ui-preview .preview-spacer { flex: 1; }
.ui-preview .preview-dialog { width: min(480px,calc(100vw - 32px)); max-height: calc(100dvh - 32px); margin: auto; padding: 0; overflow: visible; border: 0; border-radius: var(--ui-radius-card); background: var(--ui-color-surface); box-shadow: var(--ui-shadow-modal); color: var(--ui-color-text); }
.ui-preview .preview-dialog::backdrop { background: var(--ui-color-mask); backdrop-filter: blur(2px); }
.ui-preview .preview-dialog header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 20px 24px; }
.ui-preview .preview-dialog h2 { margin: 0; font-size: var(--ui-font-size-heading); font-weight: 780; }
.ui-preview .preview-dialog-body { display: grid; gap: 20px; padding: 4px 24px 24px; }
@media(max-width:900px) { .ui-preview .preview-presets { grid-template-columns: repeat(3,minmax(0,1fr)); } }
@media(max-width:600px) { .ui-preview { padding: 28px 16px; }.ui-preview .preview-heading h1 { font-size: 23px; }.ui-preview .preview-card { padding: 18px; }.ui-preview .preview-grid,.ui-preview .preview-grid.three { grid-template-columns: 1fr; }.ui-preview .preview-section-title>span { display: none; }.ui-preview .preview-footer { align-items: flex-start; flex-direction: column; } }
</style>
