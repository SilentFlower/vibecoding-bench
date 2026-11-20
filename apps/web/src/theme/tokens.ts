/** 主题种子、预设与派生：种子 → 完整 `--ui-*` 变量集。纯函数，不访问 DOM，可直接由 node:test 加载。 */
import { contrast, darkenUntil, isHexColor, lightenUntil, mix, shiftLightness, withAlpha } from './color.ts';

export type ThemeSurface = 'default' | 'soft';

/** 实际生效的深浅；由主题模式与系统偏好解析得到。 */
export type ThemeScheme = 'light' | 'dark';

/** 浏览器内保存的主题种子；任一字段非法时整体回退默认主题。 */
export interface ThemeSeed {
  version: 1;
  primary: string;
  success: string;
  warning: string;
  danger: string;
  info: string;
  surface: ThemeSurface;
  fontSize: number;
  spaceUnit: number;
  controlHeight: number;
  sizeStep: number;
  radius: number;
  shadow: number;
}

/** CSS 自定义属性名到取值的映射。 */
export type ThemeVars = Record<string, string>;

/** 数值种子字段。 */
export type NumericSeed = 'fontSize' | 'spaceUnit' | 'controlHeight' | 'sizeStep' | 'radius' | 'shadow';

/** 数值种子的取值范围，校验与主题设置界面共用。 */
export const THEME_SEED_LIMITS: Readonly<Record<NumericSeed, { min: number; max: number; step: number }>> = {
  fontSize: { min: 12, max: 16, step: 1 },
  spaceUnit: { min: 3, max: 6, step: 1 },
  controlHeight: { min: 32, max: 44, step: 1 },
  sizeStep: { min: 4, max: 8, step: 1 },
  radius: { min: 0, max: 12, step: 1 },
  shadow: { min: 0, max: 2, step: 0.25 },
};

/** 第二版浅色主题的种子。 */
export const DEFAULT_THEME_SEED: Readonly<ThemeSeed> = {
  version: 1,
  primary: '#6c54b4',
  success: '#12b981',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#5983f4',
  surface: 'default',
  fontSize: 13,
  spaceUnit: 4,
  controlHeight: 38,
  sizeStep: 6,
  radius: 8,
  shadow: 1,
};

/** 配色预设只决定主色；当前预设由主色反查，不另存预设 ID。 */
export const THEME_PRESETS = [
  { id: 'petal', name: '花瓣紫', description: '品牌默认', primary: '#6c54b4' },
  { id: 'ocean', name: '深海蓝', description: '冷静专业', primary: '#2f6bd8' },
  { id: 'teal', name: '松石绿', description: '清爽自然', primary: '#0f9f8f' },
  { id: 'dusk', name: '暮光橙', description: '温暖醒目', primary: '#e2742b' },
  { id: 'rose', name: '玫瑰红', description: '柔和亲切', primary: '#d64a7b' },
  { id: 'graphite', name: '石墨', description: '克制中性', primary: '#3d4352' },
] as const;

const WHITE = '#ffffff';
const TEXT = '#0f1527';
const SHADOW_RGB = '14, 23, 38';
// 正文对比度底线是 4.5；派生文字色以 5 为目标，与设计稿手调色组（约 5.0–6.7）的观感对齐。
const TEXT_CONTRAST = 5;
const READABLE = 4.5;
// 深色：实色（按钮、选中、进度）对卡片底的非文字对比度下限是 3，取 3.2 留余量；
// 派生文字以 5.5 为目标，深色底上观感与浅色的 5 相当。
const SOLID_CONTRAST = 3.2;
const DARK_TEXT_CONTRAST = 5.5;

interface PrimaryFamily { base: string; hover: string; container: string; text: string; ring: string; on: string }
interface ToneFamily { base: string; text: string; bg: string }

// 默认主色与功能色直接使用设计稿手调值，保证默认主题与 doc/design/console-v2 逐值一致。
const TUNED_PRIMARY: Readonly<Record<string, PrimaryFamily>> = {
  '#6c54b4': { base: '#6c54b4', hover: '#5f479f', container: '#f3f0fb', text: '#5b44a3', ring: withAlpha('#6c54b4', 0.18), on: WHITE },
};
const TUNED_TONES: Readonly<Record<string, ToneFamily>> = {
  '#12b981': { base: '#12b981', text: '#067655', bg: '#ecf9f5' },
  '#f59e0b': { base: '#f59e0b', text: '#955900', bg: '#fef7eb' },
  '#ef4444': { base: '#ef4444', text: '#c32d32', bg: '#fef0f0' },
  '#5983f4': { base: '#5983f4', text: '#3f5fcb', bg: '#f2f5fe' },
};

// 终端配色两种模式相同：底色取各自模式的墨色，ANSI 色取功能色的亮色版本，在两种墨底上都可读。
const TERMINAL = {
  'term-fg': '#d9dbe8', 'term-dim': '#8a8ea6', 'term-cursor': '#ed6ea7', 'term-red': '#f47174', 'term-green': '#4cd6a3',
  'term-yellow': '#f7b94d', 'term-blue': '#8fadf8', 'term-magenta': '#c3a6f5', 'term-cyan': '#5fd1d7',
} as const;

// 不随主题变化的中性、平台与品牌色；柔光材质只调整其中的底色组。
const NEUTRALS = {
  layout: '#f5f6fa', surface: WHITE, fill: 'rgba(98, 96, 158, 0.075)', 'fill-hover': 'rgba(98, 96, 158, 0.11)',
  'fill-muted': '#f1f2f7', 'fill-subtle': '#f7f8fb', 'fill-strong': '#d8dce8', 'fill-active': '#eceef5', track: '#e9ebf3', line: '#e6e8f0',
  mask: 'rgba(14, 23, 38, 0.3)', scrollbar: '#aab2c2',
  text: TEXT, 'text-2': '#414a5c', 'text-3': '#5f6878', 'text-4': '#97a0b2',
  'table-head': '#eff1f8', 'table-stripe': '#f8f9fc', 'table-hover': '#f0f1f9',
  'neutral-text': '#535b67', 'neutral-bg': '#f1f3f7',
  'cc-text': '#9a5634', 'cc-bg': '#fbf1ea', 'agy-text': '#3f62b0', 'agy-bg': '#eef3fd',
  brand: '#ed6ea7', ink: '#191b2c', 'on-ink': WHITE, 'ink-text': '#a7abc3', 'ink-muted': '#6c708e',
  'feedback-surface': '#191b2c', 'feedback-text': WHITE, knob: WHITE, ...TERMINAL,
} as const;
const DARK_SURFACE = '#171824';
// 深色中性色「夜幕紫灰」：手调常量，取自用户确认的深色稿，与浅色同一紫灰色相；
// 墨色比卡片更深，终端与标志块仍可区分；品牌色、墨底文字与终端配色同浅色。
const NEUTRALS_DARK: Readonly<Record<keyof typeof NEUTRALS, string>> = {
  ...NEUTRALS,
  layout: '#0f1018', surface: DARK_SURFACE, fill: 'rgba(160, 162, 220, 0.085)', 'fill-hover': 'rgba(160, 162, 220, 0.13)',
  'fill-muted': '#1f2130', 'fill-subtle': '#1c1d2b', 'fill-strong': '#3a3c52', 'fill-active': '#252738', track: '#292b3c', line: '#272938',
  mask: 'rgba(3, 4, 10, 0.62)', scrollbar: '#4a4d63',
  text: '#eceef6', 'text-2': '#c5c8d6', 'text-3': '#9a9eb2', 'text-4': '#6d7188',
  'table-head': '#20222f', 'table-stripe': '#1a1b28', 'table-hover': '#232537',
  'neutral-text': '#b4b8c8', 'neutral-bg': '#252736',
  'cc-text': '#eaa985', 'cc-bg': '#2f231f', 'agy-text': '#9db6f5', 'agy-bg': '#1e2541',
  ink: '#0a0b12', 'feedback-surface': '#272a3c', 'feedback-text': '#f3f4fa', knob: '#eceef6',
};
const SOFT_TINTED = ['layout', 'fill-muted', 'fill-subtle', 'fill-active', 'line', 'table-head', 'table-stripe', 'table-hover'] as const;

/**
 * 派生主色组；按钮文字先取白色，再取正文深色，两者都不足 4.5 时压暗主色直到白字达标。
 * @param color 种子主色。
 * @return 主色组。
 */
function primaryFamily(color: string): PrimaryFamily {
  const tuned = TUNED_PRIMARY[color];
  if (tuned) return tuned;
  let base = color;
  let on = WHITE;
  if (contrast(WHITE, base) < READABLE) {
    if (contrast(TEXT, base) >= READABLE) on = TEXT;
    else base = darkenUntil(base, [WHITE], READABLE);
  }
  const container = mix(base, WHITE, 0.08);
  return {
    base, on, container,
    hover: shiftLightness(base, -0.05),
    text: darkenUntil(shiftLightness(base, -0.05), [container, WHITE], TEXT_CONTRAST),
    ring: withAlpha(base, 0.18),
  };
}

/**
 * 派生深色主色组；六个预设与自定义主色同一规则，默认主色同样走推导。
 * 实色先提亮到对卡片底可辨；按钮文字先取白色，白字不足 4.5 时改深色字，深色字仍不足就继续提亮实色。
 * @param color 种子主色。
 * @return 主色组。
 */
function primaryFamilyDark(color: string): PrimaryFamily {
  let base = lightenUntil(color, [DARK_SURFACE], SOLID_CONTRAST);
  let on = WHITE;
  if (contrast(WHITE, base) < READABLE) {
    on = TEXT;
    base = lightenUntil(base, [TEXT], READABLE);
  }
  const container = mix(base, DARK_SURFACE, 0.2);
  return {
    base, on, container,
    hover: shiftLightness(base, 0.05),
    text: lightenUntil(shiftLightness(base, 0.1), [container, DARK_SURFACE], DARK_TEXT_CONTRAST),
    ring: withAlpha(base, 0.35),
  };
}

/** 派生深色功能色组：实色提亮到可辨，浅底改为实色压进卡片底，文字提亮到目标对比度。@param color 种子色。@return 功能色组。 */
function toneFamilyDark(color: string): ToneFamily {
  const base = lightenUntil(color, [DARK_SURFACE], SOLID_CONTRAST);
  const bg = mix(base, DARK_SURFACE, 0.14);
  return { base, bg, text: lightenUntil(shiftLightness(base, 0.06), [bg, DARK_SURFACE], DARK_TEXT_CONTRAST) };
}

/** 派生功能色组（实色、文字、浅底）。@param color 种子色。@return 功能色组。 */
function toneFamily(color: string): ToneFamily {
  const tuned = TUNED_TONES[color];
  if (tuned) return tuned;
  const bg = mix(color, WHITE, 0.08);
  return { base: color, bg, text: darkenUntil(shiftLightness(color, -0.05), [bg, WHITE], TEXT_CONTRAST) };
}

/** 按阴影强度缩放透明度，不超过 1。@param value 基准透明度。@param strength 强度倍数。@return 规范数值。 */
function fade(value: number, strength: number): number {
  return Number(Math.min(1, value * strength).toFixed(3));
}

/**
 * 派生阴影组。深色下阴影几乎不可见：底色取纯黑并加深透明度，卡片靠明度分层；
 * 浮层与弹窗另加一圈极淡的亮描边，侧栏与应用栏改为 1px 亮线。
 * @param s 阴影强度。
 * @param card 卡片阴影强度（柔光材质减半）。
 * @param scheme 深浅。
 * @return 阴影变量。
 */
function shadows(s: number, card: number, scheme: ThemeScheme): ThemeVars {
  if (scheme === 'dark') {
    const ring = `0 0 0 1px rgba(255, 255, 255, ${fade(0.07, s)})`;
    return {
      '--ui-shadow-card': `0 1px 2px rgba(0, 0, 0, ${fade(0.3, card)}), 0 10px 22px -18px rgba(0, 0, 0, ${fade(0.7, card)})`,
      '--ui-shadow-pop': `${ring}, 0 8px 24px -8px rgba(0, 0, 0, ${fade(0.65, s)})`,
      '--ui-shadow-modal': `${ring}, 0 24px 60px -20px rgba(0, 0, 0, ${fade(0.8, s)})`,
      '--ui-shadow-raised': `0 1px 3px rgba(0, 0, 0, ${fade(0.45, s)})`,
      '--ui-shadow-knob': `0 1px 2px rgba(0, 0, 0, ${fade(0.45, s)})`,
      '--ui-shadow-side': `1px 0 0 rgba(255, 255, 255, ${fade(0.045, s)})`,
      '--ui-shadow-bar': `0 1px 0 rgba(255, 255, 255, ${fade(0.05, s)})`,
    };
  }
  return {
    '--ui-shadow-card': `0 1px 2px rgba(${SHADOW_RGB}, ${fade(0.03, card)}), 0 10px 22px -18px rgba(${SHADOW_RGB}, ${fade(0.12, card)})`,
    '--ui-shadow-pop': `0 1px 6px -1px rgba(${SHADOW_RGB}, ${fade(0.09, s)}), 0 8px 20px -10px rgba(${SHADOW_RGB}, ${fade(0.08, s)})`,
    '--ui-shadow-modal': `0 24px 60px -20px rgba(${SHADOW_RGB}, ${fade(0.35, s)})`,
    '--ui-shadow-raised': `0 1px 3px rgba(${SHADOW_RGB}, ${fade(0.08, s)})`,
    '--ui-shadow-knob': `0 1px 2px rgba(0, 0, 0, ${fade(0.18, s)})`,
    '--ui-shadow-side': `2px 0 12px -10px rgba(${SHADOW_RGB}, ${fade(0.12, s)})`,
    '--ui-shadow-bar': `0 2px 12px -10px rgba(${SHADOW_RGB}, ${fade(0.2, s)})`,
  };
}

/**
 * 由种子派生完整的可主题化变量集；输出键集合固定（两种深浅相同），整组覆盖不会残留旧值。
 * @param seed 已校验的主题种子。
 * @param scheme 深浅，默认浅色。
 * @return `--ui-*` 变量映射。
 */
export function createTheme(seed: ThemeSeed, scheme: ThemeScheme = 'light'): ThemeVars {
  const vars: ThemeVars = {};
  const dark = scheme === 'dark';
  const primary = dark ? primaryFamilyDark(seed.primary) : primaryFamily(seed.primary);
  const base = dark ? NEUTRALS_DARK : NEUTRALS;
  const neutrals: Record<string, string> = { ...base };
  // 柔光：底色组向主色色相轻微偏移，卡片阴影减半，文字与控件保持不变。
  if (seed.surface === 'soft') for (const key of SOFT_TINTED) neutrals[key] = mix(primary.base, base[key], 0.04);
  for (const [key, value] of Object.entries(neutrals)) vars[`--ui-color-${key}`] = value;
  Object.assign(vars, {
    '--ui-color-primary': primary.base,
    '--ui-color-primary-hover': primary.hover,
    '--ui-color-primary-container': primary.container,
    '--ui-color-primary-text': primary.text,
    '--ui-color-primary-ring': primary.ring,
    '--ui-color-on-primary': primary.on,
  });
  for (const name of ['success', 'warning', 'danger', 'info'] as const) {
    const tone = dark ? toneFamilyDark(seed[name]) : toneFamily(seed[name]);
    vars[`--ui-color-${name}`] = tone.base;
    vars[`--ui-color-${name}-text`] = tone.text;
    vars[`--ui-color-${name}-bg`] = tone.bg;
  }
  const s = seed.shadow;
  Object.assign(vars, shadows(s, seed.surface === 'soft' ? s / 2 : s, scheme), {
    '--ui-radius-btn': `${Math.max(seed.radius - 2, 0)}px`,
    '--ui-radius-control': `${seed.radius}px`,
    '--ui-radius-block': `${seed.radius + 4}px`,
    '--ui-radius-card': `${seed.radius + 10}px`,
    // 字号与控件高只写种子级数值，三档阅读尺寸由 ui-foundation.css 的 calc 叠加。
    '--ui-font-size-base': `${seed.fontSize}px`,
    '--ui-control-base': `${seed.controlHeight}px`,
    '--ui-size-step': `${seed.sizeStep}px`,
    '--ui-space-unit': `${seed.spaceUnit}px`,
  });
  return vars;
}

/** 判断数值是否落在范围内且对齐步长，种子校验与主题设置页共用。@param value 输入。@param key 种子字段。@return 是否合法。 */
export function isValidSeedNumber(value: unknown, key: NumericSeed): value is number {
  const { min, max, step } = THEME_SEED_LIMITS[key];
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) return false;
  return Math.abs(Math.round((value - min) / step) * step + min - value) < 1e-9;
}

/**
 * 校验存储或界面传入的种子；任一字段不符整体返回 null，未知字段忽略。
 * @param value 任意输入。
 * @return 规范种子或 null。
 */
export function parseThemeSeed(value: unknown): ThemeSeed | null {
  if (!value || typeof value !== 'object') return null;
  const input = value as Record<string, unknown>;
  if (input.version !== 1 || (input.surface !== 'default' && input.surface !== 'soft')) return null;
  const colors = ['primary', 'success', 'warning', 'danger', 'info'] as const;
  if (!colors.every(key => isHexColor(input[key]))) return null;
  const numbers = Object.keys(THEME_SEED_LIMITS) as NumericSeed[];
  if (!numbers.every(key => isValidSeedNumber(input[key], key))) return null;
  const seed = { version: 1, surface: input.surface } as ThemeSeed;
  for (const key of colors) seed[key] = input[key] as string;
  for (const key of numbers) seed[key] = input[key] as number;
  return seed;
}
