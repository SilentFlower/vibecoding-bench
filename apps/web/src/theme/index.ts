/** 控制台主题：种子派生、预设、编辑器纯函数与浏览器运行时的统一入口。 */
export { DEFAULT_THEME_SEED, THEME_PRESETS, THEME_SEED_LIMITS, createTheme, isValidSeedNumber, parseThemeSeed } from './tokens.ts';
export type { NumericSeed, ThemeSeed, ThemeSurface, ThemeVars } from './tokens.ts';
export { THEME_SEED_KEYS, changedSeedKeys, normalizeHexInput, parseSeedNumber, presetIdOf } from './editor.ts';
export type { ColorSeed, ThemePresetId, ThemeSeedKey } from './editor.ts';
export { THEME_STORAGE_KEY, applyTheme, initTheme, readStoredTheme, writeStoredTheme } from './runtime.ts';
