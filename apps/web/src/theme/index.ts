/** 控制台主题：种子派生、预设与浏览器运行时的统一入口。 */
export { DEFAULT_THEME_SEED, THEME_PRESETS, THEME_SEED_LIMITS, createTheme, parseThemeSeed } from './tokens.ts';
export type { ThemeSeed, ThemeSurface, ThemeVars } from './tokens.ts';
export { THEME_STORAGE_KEY, applyTheme, initTheme, readStoredTheme, writeStoredTheme } from './runtime.ts';
