/** 主题浏览器运行时：读取、保存并应用主题种子与主题模式。只在调用时访问存储与 DOM。 */
import { DEFAULT_THEME_SEED, createTheme, parseThemeSeed, type ThemeScheme, type ThemeSeed, type ThemeVars } from './tokens.ts';

/** 主题模式：跟随系统、浅色、深色。 */
export type ThemeMode = 'system' | ThemeScheme;

/** 当前浏览器保存主题种子的存储键。 */
export const THEME_STORAGE_KEY = 'flower2api.theme';
/**
 * 当前浏览器保存主题模式的存储键，与种子分开：种子格式保持 version 1 不用迁移，种子损坏不影响模式，
 * 独立 /runtime/ 文档与两份 index.html 的首帧脚本只需读这一个键（键名由单测校验一致）。
 */
export const THEME_MODE_STORAGE_KEY = 'flower2api.theme-mode';
const DARK_QUERY = '(prefers-color-scheme: dark)';

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

/**
 * 读取已保存的主题模式；缺失、非法或存储不可用都按跟随系统处理。
 * @param storage 存储实现，默认 localStorage。
 * @return 主题模式。
 */
export function readThemeMode(storage: Pick<Storage, 'getItem'> | undefined = defaultStorage()): ThemeMode {
  try {
    const raw = storage?.getItem(THEME_MODE_STORAGE_KEY);
    return raw === 'light' || raw === 'dark' ? raw : 'system';
  } catch {
    return 'system';
  }
}

/**
 * 保存主题模式；跟随系统是默认值，删除该键，与「默认主题不写存储」一致。
 * @param mode 主题模式。
 * @param storage 存储实现，默认 localStorage。
 * @return 是否写入成功。
 */
export function writeThemeMode(mode: ThemeMode, storage: Pick<Storage, 'setItem' | 'removeItem'> | undefined = defaultStorage()): boolean {
  try {
    if (!storage) return false;
    if (mode === 'system') storage.removeItem(THEME_MODE_STORAGE_KEY);
    else storage.setItem(THEME_MODE_STORAGE_KEY, mode);
    return true;
  } catch {
    return false;
  }
}

/** 解析实际深浅。@param mode 主题模式。@param prefersDark 系统是否偏好深色。@return 深浅。 */
export function resolveScheme(mode: ThemeMode, prefersDark: boolean): ThemeScheme {
  return mode === 'system' ? (prefersDark ? 'dark' : 'light') : mode;
}

/** 系统偏好查询；不支持 matchMedia 的环境按浅色处理。@return 媒体查询或 undefined。 */
function darkQuery(): MediaQueryList | undefined {
  return typeof matchMedia === 'function' ? matchMedia(DARK_QUERY) : undefined;
}

// 本次页面会话正在使用的模式：保存失败时界面仍按本次选择显示，系统偏好变化也按它决定是否跟随。
let currentMode: ThemeMode = 'system';
const modeListeners = new Set<(mode: ThemeMode) => void>();

/** 当前使用的主题模式。@return 主题模式。 */
export function currentThemeMode(): ThemeMode {
  return currentMode;
}

/** 文档根当前的深浅（首帧脚本或运行时写入的 data-ui-scheme）。@return 深浅。 */
export function currentScheme(): ThemeScheme {
  return document.documentElement.dataset.uiScheme === 'dark' ? 'dark' : 'light';
}

/** 订阅本次会话主题模式的变化（启动应用、切换模式）。@param listener 回调，参数为新的模式。@return 取消订阅函数。 */
export function onThemeModeChange(listener: (mode: ThemeMode) => void): () => void {
  modeListeners.add(listener);
  return () => modeListeners.delete(listener);
}

/**
 * 按模式重写文档根：写 data-ui-scheme，并按深浅重新派生已保存的种子。
 * 没有保存种子但根上已有内联变量时（例如本次会话保存过默认主题）同样整组重写，否则会残留另一种深浅的值；
 * 两者都没有时由 ui-foundation.css 按 data-ui-scheme 给出默认值。
 * @param mode 主题模式。
 * @return 无。
 */
function applyMode(mode: ThemeMode): void {
  currentMode = mode;
  const root = document.documentElement;
  const scheme = resolveScheme(mode, darkQuery()?.matches ?? false);
  root.dataset.uiScheme = scheme;
  const seed = readStoredTheme();
  if (seed || root.hasAttribute('data-ui-theme')) applyTheme(root, createTheme(seed ?? DEFAULT_THEME_SEED, scheme));
  for (const listener of modeListeners) listener(mode);
}

/**
 * 保存并应用主题模式；保存失败时仍按本次选择显示，由调用方提示。
 * @param mode 主题模式。
 * @return 是否保存成功。
 */
export function setThemeMode(mode: ThemeMode): boolean {
  const saved = writeThemeMode(mode);
  applyMode(mode);
  return saved;
}

/**
 * 只应用、不保存主题模式：主题设置页先写好种子与模式两份存储，都成功后再统一应用。
 * @param mode 主题模式。
 * @return 无。
 */
export function applyThemeMode(mode: ThemeMode): void {
  applyMode(mode);
}

/**
 * 挂载前应用已保存的模式与主题，避免界面先以默认主题渲染；并订阅系统偏好，跟随系统时无需刷新即切换深浅。
 * 首帧的 data-ui-scheme 已由 index.html 的内联脚本写好，这里按同一规则再解析一次。
 * 嵌在主题设置页画板（iframe）里时深浅与变量由父页面按草稿写入，不自行跟随，否则系统切换时会用已保存值覆盖草稿预览。
 * @return 无。
 */
export function initTheme(): void {
  applyMode(readThemeMode());
  if (window.parent !== window) return;
  darkQuery()?.addEventListener('change', () => {
    if (currentMode === 'system') applyMode('system');
  });
}
