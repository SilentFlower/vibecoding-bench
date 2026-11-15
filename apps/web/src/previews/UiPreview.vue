<script setup lang="ts">
import { ref } from 'vue';
import { NumberInput, ChoiceSelect, InfoTooltip, SearchInput } from '@/components/ui/controls';
import type { ChoiceOption } from '@/components/ui/controls';

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
</script>

<template>
  <main class="ui-preview">
    <header class="preview-heading"><span>flower2api / UI COMPONENTS</span><h1>让页面共享同一套细节</h1><p>数字输入、单选菜单、信息气泡与搜索输入 · 本地交互示例</p></header>
    <form class="preview-card" @submit.prevent="save">
      <div class="preview-section-title"><h2>表单控件</h2><span>40px 高度 · 轻量焦点</span></div>
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
      <div class="preview-footer"><p>输入范围与必填由原生表单校验；空选项保留空字符串。</p><button class="preview-button primary" type="submit">保存示例</button></div>
      <pre data-testid="form-result">{{ submitted }}</pre>
    </form>
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
    <section class="preview-card"><div class="preview-section-title"><h2>浮层中的组件</h2><span>保持菜单与气泡的正确层级</span></div><p class="preview-help">同一组组件可放入编辑窗口，支持键盘关闭及焦点返回。</p><button class="preview-button" type="button" @click="dialog?.showModal()">打开窗口示例</button></section>
    <dialog ref="dialog" class="preview-dialog" aria-labelledby="preview-dialog-title">
      <header><h2 id="preview-dialog-title">授权登录 · 组件示例</h2><button class="preview-button" aria-label="关闭窗口" type="button" @click="dialog?.close()">关闭</button></header>
      <div class="preview-dialog-body">
        <ChoiceSelect v-model="dialogChoice" :options="authOptions" label="窗口内授权方式" :portal-target="dialog" />
        <NumberInput v-model="concurrency" label="窗口内并发上限" :min="1" :max="10" />
        <InfoTooltip label="查看授权说明" title="授权方式" :portal-target="dialog"><template #trigger>查看授权说明</template><p>账号配置由任务或工程创建流程提供，当前为本地组件演示。</p></InfoTooltip>
      </div>
    </dialog>
  </main>
</template>

<style scoped>
.ui-preview { max-width: 960px; margin: 0 auto; padding: 52px 26px; font-family: var(--ui-font); color: var(--ui-text); }
.preview-heading { margin-bottom: 30px; }
.preview-heading>span { font-size: 11px; color: var(--ui-accent); letter-spacing: 1.2px; }
.preview-heading h1 { font-size: 28px; font-weight: 650; margin: 12px 0 8px; }
.preview-heading p { font-size: 13px; color: var(--ui-muted); }
.preview-card { border: 1px solid var(--ui-border); border-radius: 14px; background: var(--ui-surface); padding: 26px; margin-bottom: 20px; }
.preview-section-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 24px; }
.preview-section-title h2 { font-size: 15px; font-weight: 600; margin: 0; }
.preview-section-title>span { color: var(--ui-muted); font-size: 11px; }
.preview-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 22px 18px; margin-bottom: 24px; }
.preview-grid.three { grid-template-columns: repeat(3,minmax(0,1fr)); }
.preview-footer { border-top: 1px solid var(--ui-border); padding-top: 20px; display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.preview-footer p, .preview-help { font-size: 11px; color: var(--ui-muted); line-height: 1.8; }
.preview-help { margin: 12px 0; }
.preview-button { border: 1px solid var(--ui-border); border-radius: 7px; padding: 8px 13px; background: #fff; font-size: 12px; cursor: pointer; }
.preview-button.primary { background: #303747; color: #fff; border-color: #303747; }
pre { font-size: 11px; color: var(--ui-muted); padding: 12px; border-radius: 7px; background: var(--ui-field-surface); white-space: pre-wrap; margin-top: 18px; }
.preview-summary { display: block; max-width: min(320px,70vw); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.preview-tooltip-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.preview-tooltip-grid dt { font-size: 11px; color: var(--ui-muted); }
.preview-tooltip-grid dd { margin: 3px 0 0; font-size: 13px; }
.preview-dialog { margin: auto; padding: 0; width: min(480px,calc(100vw - 32px)); max-height: calc(100dvh - 32px); border: 1px solid var(--ui-border); border-radius: 16px; overflow: visible; color: var(--ui-text); }
.preview-dialog::backdrop { background: #25273355; backdrop-filter: blur(3px); }
.preview-dialog header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 20px; border-bottom: 1px solid var(--ui-border); }
.preview-dialog h2 { font-size: 16px; font-weight: 600; }
.preview-dialog-body { display: grid; gap: 22px; padding: 24px; }
@media(max-width:600px) { .ui-preview { padding: 28px 16px; }.preview-heading h1 { font-size: 23px; }.preview-card { padding: 20px; }.preview-grid,.preview-grid.three { grid-template-columns: 1fr; }.preview-section-title>span { display: none; }.preview-footer { align-items: flex-start; flex-direction: column; } }
</style>
