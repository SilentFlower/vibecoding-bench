/** 主题浏览器运行时：读取、保存并应用主题种子。只在调用时访问存储与 DOM。 */
import { createTheme, parseThemeSeed, type ThemeSeed, type ThemeVars } from './tokens.ts';

/** 当前浏览器保存主题种子的存储键。 */
export const THEME_STORAGE_KEY = 'flower2api.theme';

/** 解析存储读取器，隐私模式或禁用存储时访问 localStorage 本身也会抛错。@return 存储或 undefined。 */
function defaultStorage(): Storage | undefined {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}

/**
 * 读取已保存的主题种子；缺失、损坏、越界或存储不可用都返回 null，由 CSS 默认值生效。
 * @param storage 存储实现，默认 localStorage。
 * @return 有效种子或 null。
 */
export function readStoredTheme(storage: Pick<Storage, 'getItem'> | undefined = defaultStorage()): ThemeSeed | null {
  try {
    const raw = storage?.getItem(THEME_STORAGE_KEY);
    return raw ? parseThemeSeed(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

/**
 * 保存主题种子；传 null 清除保存值，回到默认主题。
 * @param seed 已校验的种子或 null。
 * @param storage 存储实现，默认 localStorage。
 * @return 是否写入成功。
 */
export function writeStoredTheme(seed: ThemeSeed | null, storage: Pick<Storage, 'setItem' | 'removeItem'> | undefined = defaultStorage()): boolean {
  try {
    if (!storage) return false;
    if (seed) storage.setItem(THEME_STORAGE_KEY, JSON.stringify(seed));
    else storage.removeItem(THEME_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

/**
 * 把变量写到元素上并标记 data-ui-theme，使 ui-foundation.css 的派生字号、控件高在该元素上重新计算。
 * 用在文档根即全局主题；用在容器上只影响其子树。
 * @param element 目标元素。
 * @param vars createTheme 的输出。
 * @return 无。
 */
export function applyTheme(element: HTMLElement, vars: ThemeVars): void {
  for (const [name, value] of Object.entries(vars)) element.style.setProperty(name, value);
  element.setAttribute('data-ui-theme', '');
}

/** 挂载前应用已保存的主题，避免界面先以默认主题渲染。没有有效保存值时不写任何内联变量。@return 无。 */
export function initTheme(): void {
  const seed = readStoredTheme();
  if (seed) applyTheme(document.documentElement, createTheme(seed));
}
