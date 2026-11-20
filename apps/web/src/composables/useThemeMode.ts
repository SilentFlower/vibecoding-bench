import { readonly, ref } from 'vue';
import { currentScheme, currentThemeMode, onThemeModeChange, setThemeMode, type ThemeMode, type ThemeScheme } from '../theme';
import { useToast } from './useToast';

// 模块级共享状态：侧栏快捷切换与主题设置页看到同一份模式与深浅。
const mode = ref<ThemeMode>(currentThemeMode());
const scheme = ref<ThemeScheme>(currentScheme());
onThemeModeChange(next => { mode.value = next; });
// 深浅以文档根的 data-ui-scheme 为准：系统偏好变化、切换模式，以及主题画板由父页面直接改写 iframe 根时都能同步。
new MutationObserver(() => { scheme.value = currentScheme(); })
  .observe(document.documentElement, { attributes: true, attributeFilter: ['data-ui-scheme'] });

/**
 * 保存并应用主题模式；存储不可用时提示失败，界面仍按本次选择显示。
 * @param next 主题模式。
 * @return 是否保存成功。
 */
function setMode(next: ThemeMode): boolean {
  const saved = setThemeMode(next);
  if (!saved) useToast().show('当前浏览器无法保存主题模式，刷新后不会保持', 'warning');
  return saved;
}

/**
 * 提供当前主题模式、实际深浅与切换方法。
 * @return 只读的 mode、scheme 与 setMode。
 */
export function useThemeMode() {
  return { mode: readonly(mode), scheme: readonly(scheme), setMode };
}
