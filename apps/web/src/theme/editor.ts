/** 主题设置页的编辑器纯函数：可编辑字段、草稿差异、输入规整与校验。不访问 DOM，可直接由 node:test 加载。 */
import { isHexColor } from './color.ts';
import { THEME_PRESETS, isValidSeedNumber, type NumericSeed, type ThemeSeed } from './tokens.ts';

/** 可编辑的种子字段（版本号不可编辑）。 */
export type ThemeSeedKey = Exclude<keyof ThemeSeed, 'version'>;

/** 颜色种子字段。 */
export type ColorSeed = 'primary' | 'success' | 'warning' | 'danger' | 'info';

/** 预设 ID。 */
export type ThemePresetId = (typeof THEME_PRESETS)[number]['id'];

/** 全部可编辑字段，顺序即界面顺序；待应用数按这些字段逐一比较。 */
export const THEME_SEED_KEYS: readonly ThemeSeedKey[] = [
  'primary', 'success', 'warning', 'danger', 'info', 'surface',
  'fontSize', 'controlHeight', 'sizeStep', 'spaceUnit', 'radius', 'shadow',
];

/**
 * 列出两份种子取值不同的字段。
 * @param draft 草稿种子。
 * @param saved 对照种子（已保存或默认）。
 * @return 不同的字段，按 THEME_SEED_KEYS 顺序。
 */
export function changedSeedKeys(draft: ThemeSeed, saved: ThemeSeed): ThemeSeedKey[] {
  return THEME_SEED_KEYS.filter(key => draft[key] !== saved[key]);
}

const shortHex = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/;

/**
 * 把用户输入的颜色规整为种子要求的 6 位小写 hex；接受大小写的 #rgb 与 #rrggbb，首尾空白忽略。
 * @param text 输入文本。
 * @return 规整后的颜色，格式不符返回 null。
 */
export function normalizeHexInput(text: string): string | null {
  const value = text.trim().toLowerCase();
  const short = shortHex.exec(value);
  const hex = short ? `#${short[1]}${short[1]}${short[2]}${short[2]}${short[3]}${short[3]}` : value;
  return isHexColor(hex) ? hex : null;
}

/**
 * 解析数值字段的输入；与种子校验同一规则，不钳制越界值。
 * @param key 数值字段。
 * @param input 数字输入组件的值，清空时为空字符串。
 * @return 合法数值，空、非数、越界或不对齐步长返回 null。
 */
export function parseSeedNumber(key: NumericSeed, input: string | number): number | null {
  // Number('') 为 0，清空必须先单独拦下，否则会被当成合法的圆角 0。
  if (typeof input === 'string' && input.trim() === '') return null;
  const value = typeof input === 'number' ? input : Number(input);
  return isValidSeedNumber(value, key) ? value : null;
}

/**
 * 由主色反查预设；预设只决定主色，所以主色就是唯一依据。
 * @param primary 种子主色。
 * @return 预设 ID，自定义主色返回 null。
 */
export function presetIdOf(primary: string): ThemePresetId | null {
  return THEME_PRESETS.find(preset => preset.primary === primary)?.id ?? null;
}
