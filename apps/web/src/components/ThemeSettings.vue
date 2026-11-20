<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import { PageHeader } from '@/components/ui/page-header';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Segmented } from '@/components/ui/segmented';
import { NumberInput } from '@/components/ui/controls';
import { ConfirmationDialog } from '@/components/ui/feedback';
import { Check, RotateCcw, Save, Undo } from '@/components/ui/icon';
import {
  DEFAULT_THEME_SEED, THEME_PRESETS, THEME_SEED_LIMITS, applyTheme, changedSeedKeys, createTheme, normalizeHexInput, parseSeedNumber, presetIdOf, readStoredTheme, writeStoredTheme,
  type ColorSeed, type NumericSeed, type ThemeSeed, type ThemeSeedKey, type ThemeSurface,
} from '@/theme';
import { useToast } from '../composables/useToast';
import ThemePreview from './theme/ThemePreview.vue';
import '../theme-settings.css';

/** 主题设置页：编辑当前浏览器的主题种子草稿，在隔离画板预览，保存后应用到整个控制台。 */
type Category = 'color' | 'size' | 'style';
type EditableField = ColorSeed | NumericSeed;
interface NumberField { key: NumericSeed; label: string; unit: string; help: string }

const colorFields: readonly { key: ColorSeed; label: string; help: string }[] = [
  { key: 'primary', label: '品牌主色', help: '完整色阶与界面基调' },
  { key: 'success', label: '成功色', help: '成功反馈与状态' },
  { key: 'warning', label: '警告色', help: '额度与风险提醒' },
  { key: 'danger', label: '错误色', help: '失败与破坏性操作' },
  { key: 'info', label: '信息色', help: '系统与请求信息' },
];
const numberFields: Readonly<Record<Exclude<Category, 'color'>, readonly NumberField[]>> = {
  size: [
    { key: 'fontSize', label: '基础字号', unit: 'px', help: '正文、按钮与输入框的字号' },
    { key: 'controlHeight', label: '控件高度', unit: 'px', help: '中号按钮与输入框的高度' },
    { key: 'sizeStep', label: '尺寸步长', unit: 'px', help: '小号、大号控件与中号的高度差' },
    { key: 'spaceUnit', label: '基础间距', unit: 'px', help: '组件内边距与间隙的单位' },
  ],
  style: [
    { key: 'radius', label: '通用圆角', unit: 'px', help: '控件圆角；按钮、内块与卡片按它递增' },
    { key: 'shadow', label: '阴影强度', unit: '倍', help: '卡片、浮层与弹窗阴影的浓淡' },
  ],
};
const surfaceOptions = [{ value: 'default', label: '默认' }, { value: 'soft', label: '柔光' }] as const;
const categories: readonly { value: Category; label: string; keys: readonly EditableField[] }[] = [
  { value: 'color', label: '颜色', keys: colorFields.map(field => field.key) },
  { value: 'size', label: '尺寸', keys: numberFields.size.map(field => field.key) },
  { value: 'style', label: '风格', keys: numberFields.style.map(field => field.key) },
];

const toast = useToast();
const saved = ref<ThemeSeed>({ ...(readStoredTheme() ?? DEFAULT_THEME_SEED) });
const draft = reactive<ThemeSeed>({ ...saved.value });
// 输入文本与错误只为无效或尚未规整的输入保存；无效时草稿保留上次有效值，画板不变。
const inputs = reactive<Partial<Record<EditableField, string | number>>>({});
const errors = reactive<Partial<Record<EditableField, string>>>({});
const category = ref<Category>('color');

const changed = computed(() => changedSeedKeys(draft, saved.value));
const invalidCount = computed(() => Object.keys(errors).length);
const invalid = computed(() => invalidCount.value > 0);
const dirty = computed(() => changed.value.length > 0 || invalid.value);
const atDefault = computed(() => changedSeedKeys(draft, DEFAULT_THEME_SEED).length === 0);
const activePreset = computed(() => presetIdOf(draft.primary));
// 无效输入不进草稿也不计入待应用数，单独说明，否则只有无效输入时会出现「已同步」却不能保存。
const syncLabel = computed(() => [
  changed.value.length ? `${changed.value.length} 处修改待应用` : '',
  invalidCount.value ? `${invalidCount.value} 项输入无效` : '',
].filter(Boolean).join(' · ') || '已同步');
// 分类计数与系统设置分类计数同理：切到其它分类后仍能看出哪个分类有已修改或无效的字段。
const categoryOptions = computed(() => categories.map(({ value, label, keys }) => {
  const count = keys.filter(key => marked(key)).length;
  return { value, label, count: count || undefined };
}));

/** 字段是否需要「已修改」标记与单项恢复：与已保存值不同，或输入无效。@param key 种子字段。@return 是否标记。 */
function marked(key: ThemeSeedKey): boolean {
  return changed.value.includes(key) || key in errors;
}

/** 清空输入文本与错误，界面回到草稿值。@return 无。 */
function clearInputs(): void {
  for (const key of Object.keys(inputs) as EditableField[]) delete inputs[key];
  for (const key of Object.keys(errors) as EditableField[]) delete errors[key];
}

/** 选择预设：预设只决定主色。@param primary 预设主色。@return 无。 */
function choosePreset(primary: string): void {
  draft.primary = primary;
  delete inputs.primary;
  delete errors.primary;
}

/** 取色器只产生合法颜色，直接写入草稿并清除该项文本输入。@param key 颜色字段。@param value 取色器值。@return 无。 */
function pickColor(key: ColorSeed, value: string): void {
  const color = normalizeHexInput(value);
  if (!color) return;
  draft[key] = color;
  delete inputs[key];
  delete errors[key];
}

/** 处理 hex 文本输入：合法即写入草稿，否则只记录错误。@param key 颜色字段。@param text 输入文本。@return 无。 */
function typeColor(key: ColorSeed, text: string): void {
  inputs[key] = text;
  const color = normalizeHexInput(text);
  if (color) {
    draft[key] = color;
    delete errors[key];
  } else {
    errors[key] = '请输入 #rgb 或 #rrggbb 格式的颜色';
  }
}

/** 输入框确认后，合法输入显示规整后的 6 位小写值。@param key 颜色字段。@return 无。 */
function settleColor(key: ColorSeed): void {
  if (!(key in errors)) delete inputs[key];
}

/** 处理数值输入：清空、越界或不对齐步长都不写入草稿，并提示允许范围。@param key 数值字段。@param input 输入值。@return 无。 */
function typeNumber(key: NumericSeed, input: string | number): void {
  inputs[key] = input;
  const value = parseSeedNumber(key, input);
  if (value === null) {
    const { min, max, step } = THEME_SEED_LIMITS[key];
    errors[key] = step < 1 ? `请输入 ${min}–${max} 之间、步长 ${step} 的数值` : `请输入 ${min}–${max} 之间的整数`;
  } else {
    draft[key] = value;
    delete errors[key];
  }
}

/** 单项恢复为已保存值。@param key 种子字段。@return 无。 */
function restoreField(key: ThemeSeedKey): void {
  (draft as Record<ThemeSeedKey, unknown>)[key] = saved.value[key];
  if (key !== 'surface') {
    delete inputs[key];
    delete errors[key];
  }
}

/** 撤销草稿，回到已保存主题。@return 无。 */
function discardDraft(): void {
  Object.assign(draft, saved.value);
  clearInputs();
}

/** 草稿回到第二版默认主题；仍需保存才生效。@return 无。 */
function resetDefault(): void {
  Object.assign(draft, DEFAULT_THEME_SEED);
  clearInputs();
}

/** 保存草稿并应用到整个控制台；存储写入失败时控制台不变、草稿保留。@return 无。 */
function save(): void {
  if (!changed.value.length || invalid.value) return;
  const seed: ThemeSeed = { ...draft };
  // 默认主题不占存储：清除后由 CSS 默认值生效，存储损坏的旧值也随之消失。
  if (!writeStoredTheme(atDefault.value ? null : seed)) {
    toast.show('当前浏览器无法保存主题，请检查站点存储权限后重试');
    return;
  }
  applyTheme(document.documentElement, createTheme(seed));
  saved.value = seed;
  toast.show('主题已保存并应用', 'success');
}

// 站内离开：有草稿时由确认框决定；去往登录页的退出流程已先撤销会话，拦截会让页面停在失去凭据的状态，所以直接放行。
const leaveOpen = ref(false);
let settleLeave: ((leave: boolean) => void) | undefined;
onBeforeRouteLeave(to => {
  if (!dirty.value || to.name === 'login') return true;
  leaveOpen.value = true;
  return new Promise<boolean>(resolve => { settleLeave = resolve; });
});
/** 关闭离开确认并放行或拦截导航。@param leave 是否放弃草稿离开。@return 无。 */
function answerLeave(leave: boolean): void {
  leaveOpen.value = false;
  settleLeave?.(leave);
  settleLeave = undefined;
}

/** 刷新或关闭标签页时由浏览器原生提示确认。@param event 卸载前事件。@return 无。 */
function warnUnload(event: BeforeUnloadEvent): void {
  event.preventDefault();
  event.returnValue = '';
}
watch(dirty, value => {
  if (value) window.addEventListener('beforeunload', warnUnload);
  else window.removeEventListener('beforeunload', warnUnload);
});
onBeforeUnmount(() => window.removeEventListener('beforeunload', warnUnload));
</script>

<template>
  <div class="theme-page">
    <PageHeader title="主题设置">
      <template #description>自定义当前浏览器中的控制台主题<span class="theme-sync-state" :data-dirty="dirty" :data-invalid="invalid" data-theme-sync>{{ syncLabel }}</span></template>
      <template #actions>
        <Button variant="ghost" size="sm" :disabled="!dirty" @click="discardDraft"><Undo :size="14" />撤销草稿</Button>
        <Button variant="outline" size="sm" :disabled="atDefault && !invalid" @click="resetDefault"><RotateCcw :size="14" />恢复默认</Button>
        <Button size="sm" :disabled="!changed.length || invalid" @click="save"><Save :size="14" />保存并应用</Button>
      </template>
    </PageHeader>
    <!-- 窄屏页头说明仅读屏可见，这里补一行可见状态。 -->
    <p class="theme-mobile-state" aria-hidden="true"><span class="theme-sync-state" :data-dirty="dirty" :data-invalid="invalid">{{ syncLabel }}</span></p>
    <div class="theme-layout">
      <aside class="fui-card theme-panel" aria-label="主题参数">
        <section class="theme-group">
          <h2>主题预设</h2>
          <div class="theme-presets">
            <button v-for="preset in THEME_PRESETS" :key="preset.id" type="button" :aria-pressed="activePreset === preset.id" :data-preset="preset.id" :style="{ '--theme-preset': preset.primary }" @click="choosePreset(preset.primary)">
              <i aria-hidden="true" /><b>{{ preset.name }}</b><small>{{ preset.description }}</small><Check v-if="activePreset === preset.id" :size="12" />
            </button>
          </div>
        </section>
        <section class="theme-group">
          <div class="theme-group-head">
            <h2>表面材质</h2>
            <template v-if="marked('surface')"><Badge>已修改</Badge><button type="button" class="theme-restore" aria-label="恢复已保存的表面材质" title="恢复已保存值" @click="restoreField('surface')"><Undo :size="14" /></button></template>
          </div>
          <Segmented :model-value="draft.surface" :options="surfaceOptions" label="表面材质" @update:model-value="value => draft.surface = value as ThemeSurface" />
        </section>
        <Segmented v-model="category" :options="categoryOptions" label="参数分类" />
        <div v-if="category === 'color'" class="theme-group theme-fields">
          <div v-for="field in colorFields" :key="field.key" class="theme-color-field" :data-field="field.key">
            <input type="color" class="theme-swatch" :value="draft[field.key]" :aria-label="`${field.label}取色器`" @input="event => pickColor(field.key, (event.target as HTMLInputElement).value)">
            <div class="theme-field-text">
              <div class="theme-field-label"><label :for="`theme-${field.key}`">{{ field.label }}</label><template v-if="marked(field.key)"><Badge>已修改</Badge><button type="button" class="theme-restore" :aria-label="`恢复已保存的${field.label}`" title="恢复已保存值" @click="restoreField(field.key)"><Undo :size="14" /></button></template></div>
              <small>{{ field.help }}</small>
            </div>
            <Input :id="`theme-${field.key}`" class="theme-hex" :model-value="inputs[field.key] ?? draft[field.key]" :aria-invalid="!!errors[field.key]" :aria-describedby="errors[field.key] ? `theme-${field.key}-error` : undefined" maxlength="7" spellcheck="false" autocomplete="off" @update:model-value="value => typeColor(field.key, String(value))" @change="settleColor(field.key)" />
            <p v-if="errors[field.key]" :id="`theme-${field.key}-error`" class="theme-field-error" role="alert">{{ errors[field.key] }}</p>
          </div>
        </div>
        <div v-else class="theme-group theme-fields">
          <div v-for="field in numberFields[category]" :key="field.key" class="theme-number-field" :data-field="field.key">
            <NumberInput :model-value="inputs[field.key] ?? draft[field.key]" :label="`${field.label}（${field.unit}）`" :name="`theme-${field.key}`" :min="THEME_SEED_LIMITS[field.key].min" :max="THEME_SEED_LIMITS[field.key].max" :step="THEME_SEED_LIMITS[field.key].step" :invalid="!!errors[field.key]" :aria-describedby="errors[field.key] ? `theme-${field.key}-error` : undefined" @update:model-value="value => typeNumber(field.key, value)">
              <template #label-extra><template v-if="marked(field.key)"><Badge>已修改</Badge><button type="button" class="theme-restore" :aria-label="`恢复已保存的${field.label}`" title="恢复已保存值" @click="restoreField(field.key)"><Undo :size="14" /></button></template></template>
            </NumberInput>
            <p v-if="errors[field.key]" :id="`theme-${field.key}-error`" class="theme-field-error" role="alert">{{ errors[field.key] }}</p>
            <p v-else class="fui-field-help">{{ field.help }}</p>
          </div>
        </div>
      </aside>
      <ThemePreview :seed="draft" />
    </div>
    <ConfirmationDialog :open="leaveOpen" title="放弃未保存的主题修改？" message="草稿只在本页有效，离开后丢失。" confirm-label="放弃并离开" danger @confirm="answerLeave(true)" @cancel="answerLeave(false)" />
  </div>
</template>
