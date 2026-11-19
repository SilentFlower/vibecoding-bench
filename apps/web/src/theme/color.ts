/** 主题颜色运算：hex 与 OKLab 互转、混合、明度调整与 WCAG 对比度。纯函数，不访问 DOM。 */

/** OKLab 坐标；L 为感知明度 0–1，a/b 为色度分量。 */
interface Lab { l: number; a: number; b: number }

const hexPattern = /^#[0-9a-f]{6}$/;

/** 判断是否为规范的 6 位小写 hex 颜色。@param value 任意输入。@return 是否合法。 */
export function isHexColor(value: unknown): value is string {
  return typeof value === 'string' && hexPattern.test(value);
}

/** sRGB 通道（0–1）转线性光。@param c 伽马编码通道。@return 线性值。 */
function toLinear(c: number): number {
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** 线性光转 sRGB 通道并裁剪到 0–1。@param c 线性值。@return 伽马编码通道。 */
function fromLinear(c: number): number {
  const value = c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
  return Math.min(1, Math.max(0, value));
}

/** 解析 hex 为 0–255 通道。@param hex `#rrggbb`。@return 三个通道值。 */
function channels(hex: string): [number, number, number] {
  return [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16)) as [number, number, number];
}

/** hex 转 OKLab。@param hex `#rrggbb`。@return OKLab 坐标。 */
function toLab(hex: string): Lab {
  const [r, g, b] = channels(hex).map(value => toLinear(value / 255)) as [number, number, number];
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return {
    l: 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    a: 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    b: 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  };
}

/** OKLab 转 hex；超出 sRGB 色域的通道直接裁剪。@param lab OKLab 坐标。@return `#rrggbb`。 */
function fromLab({ l, a, b }: Lab): string {
  const l3 = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m3 = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s3 = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const rgb = [
    4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3,
    -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3,
    -0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3,
  ];
  return `#${rgb.map(value => Math.round(fromLinear(value) * 255).toString(16).padStart(2, '0')).join('')}`;
}

/**
 * 在 OKLab 空间按权重混合两色，感知上比 sRGB 线性混合更均匀。
 * @param color 前景色。
 * @param base 底色。
 * @param weight 前景色占比 0–1。
 * @return 混合后的 hex。
 */
export function mix(color: string, base: string, weight: number): string {
  const front = toLab(color);
  const back = toLab(base);
  return fromLab({
    l: front.l * weight + back.l * (1 - weight),
    a: front.a * weight + back.a * (1 - weight),
    b: front.b * weight + back.b * (1 - weight),
  });
}

/**
 * 保持色相与色度，只调整感知明度。
 * @param color 原色。
 * @param delta 明度增量，负值压暗。
 * @return 调整后的 hex。
 */
export function shiftLightness(color: string, delta: number): string {
  const lab = toLab(color);
  return fromLab({ ...lab, l: Math.min(1, Math.max(0, lab.l + delta)) });
}

/** 生成带透明度的颜色值。@param color 原色。@param opacity 不透明度 0–1。@return `rgba(r, g, b, a)`。 */
export function withAlpha(color: string, opacity: number): string {
  return `rgba(${channels(color).join(', ')}, ${Number(opacity.toFixed(3))})`;
}

/** WCAG 相对亮度。@param color hex。@return 0–1 的亮度。 */
function luminance(color: string): number {
  const [r, g, b] = channels(color).map(value => toLinear(value / 255)) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2 对比度。@param first 颜色一。@param second 颜色二。@return 1–21 的对比度。 */
export function contrast(first: string, second: string): number {
  const [light, dark] = [luminance(first), luminance(second)].sort((x, y) => y - x) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

/**
 * 逐步压暗直到对全部背景都达到目标对比度；明度降到 0 时为黑色，必然达标，循环有界。
 * @param color 起始色。
 * @param backgrounds 需满足对比度的背景色。
 * @param target 目标对比度。
 * @return 满足要求的最浅颜色。
 */
export function darkenUntil(color: string, backgrounds: readonly string[], target: number): string {
  let result = color;
  for (let step = 0; step < 50 && backgrounds.some(background => contrast(result, background) < target); step++) {
    result = shiftLightness(result, -0.02);
  }
  return result;
}
