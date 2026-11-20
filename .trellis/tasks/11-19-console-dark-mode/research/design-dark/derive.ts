/**
 * 深色稿色板生成脚本：用产品的颜色函数（apps/web/src/theme/color.ts）推导深色下的主色组与功能色组，
 * 输出 palette.js 供 mock.html 的 #palette 画面与主题页使用。规则即实施时 createTheme 深色分支的原型。
 * 运行：node --experimental-strip-types --no-warnings derive.ts > palette.js
 */
import { contrast, mix, shiftLightness, withAlpha } from '../../../../../apps/web/src/theme/color.ts';

const WHITE = '#ffffff';
const DARK_ON = '#0f1527';
// 实色（按钮、选中、进度）对卡片底的非文字对比度下限是 3，取 3.2 留余量。
const SOLID = 3.2;
// 文字对比度底线 4.5；派生文字色以 5.5 为目标，深色底上观感与浅色的 5 相当。
const READABLE = 4.5;
const TEXT = 5.5;

/** 深色卡片底（夜幕紫灰）。 */
const SURFACE = '#171824';

/** 逐步提亮直到对全部背景达到目标对比度；明度到 1 为白色，循环有界。 */
function lightenUntil(color: string, backgrounds: readonly string[], target: number): string {
  let result = color;
  for (let step = 0; step < 50 && backgrounds.some(background => contrast(result, background) < target); step++) {
    result = shiftLightness(result, 0.02);
  }
  return result;
}

/** 深色主色组：实色先提亮到可辨，按钮文字先白后深，两者都不足时继续提亮直到深色字达标。 */
function primaryDark(seed: string, surface: string) {
  let base = lightenUntil(seed, [surface], SOLID);
  let on = WHITE;
  if (contrast(WHITE, base) < READABLE) {
    on = DARK_ON;
    base = brightenForDarkText(base);
  }
  const container = mix(base, surface, 0.2);
  return {
    base, on, container,
    hover: shiftLightness(base, 0.05),
    text: lightenUntil(shiftLightness(base, 0.1), [container, surface], TEXT),
    ring: withAlpha(base, 0.35),
  };
}

/** 提亮直到深色按钮文字达到 4.5。 */
function brightenForDarkText(color: string): string {
  let result = color;
  for (let step = 0; step < 50 && contrast(DARK_ON, result) < READABLE; step++) result = shiftLightness(result, 0.02);
  return result;
}

/** 深色功能色组：实色提亮到可辨，浅底改为实色压进卡片底，文字提亮到目标对比度。 */
function toneDark(seed: string, surface: string) {
  const base = lightenUntil(seed, [surface], SOLID);
  const bg = mix(base, surface, 0.14);
  return { base, bg, text: lightenUntil(shiftLightness(base, 0.06), [bg, surface], TEXT) };
}

const presets = [
  ['petal', '花瓣紫', '#6c54b4'], ['ocean', '深海蓝', '#2f6bd8'], ['teal', '松石绿', '#0f9f8f'],
  ['dusk', '暮光橙', '#e2742b'], ['rose', '玫瑰红', '#d64a7b'], ['graphite', '石墨', '#3d4352'],
] as const;
const tones = [['success', '#12b981'], ['warning', '#f59e0b'], ['danger', '#ef4444'], ['info', '#5983f4']] as const;

const output = {
  presets: presets.map(([id, name, seed]) => {
    const family = primaryDark(seed, SURFACE);
    return { id, name, seed, ...family, contrastOn: +contrast(family.on, family.base).toFixed(2), contrastBase: +contrast(family.base, SURFACE).toFixed(2), contrastText: +contrast(family.text, SURFACE).toFixed(2) };
  }),
  tones: tones.map(([id, seed]) => {
    const family = toneDark(seed, SURFACE);
    return { id, seed, ...family, contrastText: +contrast(family.text, family.bg).toFixed(2) };
  }),
};
console.log(`// 由 derive.ts 生成，勿手改。\nconst PALETTE = ${JSON.stringify(output, null, 1)};`);
