import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import test from 'node:test';
import { contrast } from '../src/theme/color.ts';
import { DEFAULT_THEME_SEED, THEME_PRESETS, createTheme, parseThemeSeed } from '../src/theme/tokens.ts';
import { THEME_STORAGE_KEY, readStoredTheme, writeStoredTheme } from '../src/theme/runtime.ts';
import { THEME_SEED_KEYS, changedSeedKeys, normalizeHexInput, parseSeedNumber, presetIdOf } from '../src/theme/editor.ts';

const foundation = readFileSync(new URL('../../legacy-web/ui-foundation.css', import.meta.url), 'utf8');
const themable = /(--ui-(?:color|shadow|radius)-[a-z0-9-]+|--ui-(?:font-size-base|control-base|size-step|space-unit))\s*:\s*([^;]+);/g;
const normalize = value => value.trim().replace(/\s+/g, ' ');
const hexOf = (vars, name) => {
  assert.match(vars[name], /^#[0-9a-f]{6}$/, name);
  return vars[name];
};

test('默认主题与 ui-foundation.css 默认值逐项一致（双向）', () => {
  const css = Object.fromEntries([...foundation.matchAll(themable)].map(([, name, value]) => [name, normalize(value)]));
  const vars = Object.fromEntries(Object.entries(createTheme(DEFAULT_THEME_SEED)).map(([name, value]) => [name, normalize(value)]));
  assert.deepEqual(css, vars);
});

test('默认主题取第二版设计稿手调值', () => {
  const vars = createTheme(DEFAULT_THEME_SEED);
  assert.equal(vars['--ui-color-primary'], '#6c54b4');
  assert.equal(vars['--ui-color-primary-hover'], '#5f479f');
  assert.equal(vars['--ui-color-primary-text'], '#5b44a3');
  assert.equal(vars['--ui-color-primary-ring'], 'rgba(108, 84, 180, 0.18)');
  assert.equal(vars['--ui-color-success-text'], '#067655');
  assert.equal(vars['--ui-color-danger-bg'], '#fef0f0');
  assert.equal(vars['--ui-shadow-card'], '0 1px 2px rgba(14, 23, 38, 0.03), 0 10px 22px -18px rgba(14, 23, 38, 0.12)');
});

test('预设与边界色派生后文字和按钮文字对比度不低于 4.5', () => {
  const colors = [...THEME_PRESETS.map(preset => preset.primary), '#ffee00', '#111111', '#ff00ff', '#00ffff', '#808080', '#ffffff'];
  for (const color of colors) {
    for (const surface of ['default', 'soft']) {
      const vars = createTheme({ ...DEFAULT_THEME_SEED, primary: color, success: color, warning: color, danger: color, info: color, surface });
      const primary = hexOf(vars, '--ui-color-primary');
      assert.ok(contrast(hexOf(vars, '--ui-color-on-primary'), primary) >= 4.5, `${color} 按钮文字`);
      for (const background of ['--ui-color-primary-container', '--ui-color-surface']) {
        assert.ok(contrast(hexOf(vars, '--ui-color-primary-text'), hexOf(vars, background)) >= 4.5, `${color} 主色文字/${background}`);
      }
      for (const tone of ['success', 'warning', 'danger', 'info']) {
        assert.ok(contrast(hexOf(vars, `--ui-color-${tone}-text`), hexOf(vars, `--ui-color-${tone}-bg`)) >= 4.5, `${color} ${tone}`);
      }
    }
  }
});

test('浅亮主色改用深色按钮文字，白字与深字都不足时压暗主色', () => {
  const dusk = createTheme({ ...DEFAULT_THEME_SEED, primary: '#e2742b' });
  assert.equal(dusk['--ui-color-primary'], '#e2742b');
  assert.equal(dusk['--ui-color-on-primary'], '#0f1527');
  const rose = createTheme({ ...DEFAULT_THEME_SEED, primary: '#d64a7b' });
  assert.equal(rose['--ui-color-on-primary'], '#ffffff');
  assert.notEqual(rose['--ui-color-primary'], '#d64a7b');
});

test('尺寸、圆角、阴影与材质按种子派生', () => {
  const vars = createTheme({ ...DEFAULT_THEME_SEED, fontSize: 15, controlHeight: 40, sizeStep: 8, spaceUnit: 5, radius: 0, shadow: 0, surface: 'soft' });
  assert.equal(vars['--ui-font-size-base'], '15px');
  assert.equal(vars['--ui-control-base'], '40px');
  assert.equal(vars['--ui-size-step'], '8px');
  assert.equal(vars['--ui-space-unit'], '5px');
  assert.deepEqual(['btn', 'control', 'block', 'card'].map(key => vars[`--ui-radius-${key}`]), ['0px', '0px', '4px', '10px']);
  assert.equal(vars['--ui-shadow-modal'], '0 24px 60px -20px rgba(14, 23, 38, 0)');
  assert.notEqual(vars['--ui-color-layout'], createTheme(DEFAULT_THEME_SEED)['--ui-color-layout']);
  assert.equal(vars['--ui-color-text'], '#0f1527');
  assert.deepEqual(Object.keys(vars).sort(), Object.keys(createTheme(DEFAULT_THEME_SEED)).sort());
});

test('种子校验：合法值通过，任一字段非法整体拒绝', () => {
  assert.deepEqual(parseThemeSeed({ ...DEFAULT_THEME_SEED, extra: true }), DEFAULT_THEME_SEED);
  assert.deepEqual(parseThemeSeed({ ...DEFAULT_THEME_SEED, shadow: 1.75 }), { ...DEFAULT_THEME_SEED, shadow: 1.75 });
  for (const patch of [
    { version: 2 }, { version: undefined }, { primary: '#6C54B4' }, { primary: 'red' }, { info: '#12345' },
    { surface: 'glass' }, { fontSize: 11 }, { fontSize: 17 }, { fontSize: 13.5 }, { radius: -1 },
    { shadow: 0.3 }, { shadow: Number.NaN }, { spaceUnit: '4' }, { controlHeight: Infinity },
  ]) assert.equal(parseThemeSeed({ ...DEFAULT_THEME_SEED, ...patch }), null, JSON.stringify(patch));
  for (const value of [null, undefined, 'x', 1, [], {}]) assert.equal(parseThemeSeed(value), null);
});

test('存储读取：缺失、损坏、越界、抛错都回退为空，合法值往返一致', () => {
  const memory = new Map();
  const storage = { getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, value), removeItem: key => memory.delete(key) };
  assert.equal(readStoredTheme(storage), null);
  memory.set(THEME_STORAGE_KEY, '{broken');
  assert.equal(readStoredTheme(storage), null);
  memory.set(THEME_STORAGE_KEY, JSON.stringify({ ...DEFAULT_THEME_SEED, radius: 99 }));
  assert.equal(readStoredTheme(storage), null);
  const seed = { ...DEFAULT_THEME_SEED, primary: '#2f6bd8' };
  assert.equal(writeStoredTheme(seed, storage), true);
  assert.deepEqual(readStoredTheme(storage), seed);
  assert.equal(writeStoredTheme(null, storage), true);
  assert.equal(readStoredTheme(storage), null);
  const broken = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); }, removeItem() { throw new Error('denied'); } };
  assert.equal(readStoredTheme(broken), null);
  assert.equal(writeStoredTheme(seed, broken), false);
  assert.equal(readStoredTheme(undefined), null);
});

test('编辑器：草稿差异按字段顺序列出', () => {
  assert.deepEqual(changedSeedKeys(DEFAULT_THEME_SEED, { ...DEFAULT_THEME_SEED }), []);
  assert.deepEqual(changedSeedKeys({ ...DEFAULT_THEME_SEED, radius: 4, primary: '#2f6bd8' }, DEFAULT_THEME_SEED), ['primary', 'radius']);
  const all = { version: 1, primary: '#2f6bd8', success: '#000001', warning: '#000002', danger: '#000003', info: '#000004', surface: 'soft', fontSize: 14, controlHeight: 40, sizeStep: 7, spaceUnit: 5, radius: 4, shadow: 1.5 };
  assert.deepEqual(changedSeedKeys(all, DEFAULT_THEME_SEED), [...THEME_SEED_KEYS]);
  assert.deepEqual([...THEME_SEED_KEYS].sort(), Object.keys(DEFAULT_THEME_SEED).filter(key => key !== 'version').sort());
});

test('编辑器：hex 输入规整为 6 位小写，格式不符拒绝', () => {
  assert.equal(normalizeHexInput('#ABC'), '#aabbcc');
  assert.equal(normalizeHexInput('#2F6BD8'), '#2f6bd8');
  assert.equal(normalizeHexInput('  #2f6bd8 '), '#2f6bd8');
  for (const text of ['2f6bd8', '#12345', '#ggg', '#12', '', '#2f6bd8ff', 'red']) assert.equal(normalizeHexInput(text), null, text);
});

test('编辑器：数值输入按种子范围与步长校验，不钳制', () => {
  assert.equal(parseSeedNumber('fontSize', '12'), 12);
  assert.equal(parseSeedNumber('fontSize', 16), 16);
  assert.equal(parseSeedNumber('radius', '0'), 0);
  assert.equal(parseSeedNumber('shadow', '1.25'), 1.25);
  for (const [key, input] of [['fontSize', '11'], ['fontSize', 17], ['fontSize', '13.5'], ['shadow', '0.3'], ['radius', ''], ['radius', '  '], ['controlHeight', 'abc'], ['spaceUnit', '7']]) {
    assert.equal(parseSeedNumber(key, input), null, `${key}=${input}`);
  }
});

test('编辑器：主色反查预设，自定义色无预设', () => {
  for (const preset of THEME_PRESETS) assert.equal(presetIdOf(preset.primary), preset.id);
  assert.equal(presetIdOf(DEFAULT_THEME_SEED.primary), 'petal');
  assert.equal(presetIdOf('#123456'), null);
});

const uiRoot = new URL('../src/components/ui/', import.meta.url);
const colorLiteral = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab)\(|\b(?:white|black)\b/;
const paletteUtility = /\b(?:bg|text|border|ring|fill|stroke|outline|from|via|to)-(?:black|white|slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)\b/;
const radiusLiteral = /^(?:0|50%|999px|inherit)$/;

/** 递归列出 components/ui 下的源码文件。 */
function sourceFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
    ? sourceFiles(new URL(`${entry.name}/`, dir))
    : /\.(?:vue|ts|css)$/.test(entry.name) ? [new URL(entry.name, dir)] : []);
}

/** 拆出 CSS 声明（属性名、取值）；忽略注释。 */
function declarations(css) {
  return [...css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([-a-zA-Z]+)\s*:\s*([^;{}]+)(?=;|})/g)].map(([, name, value]) => [name, value.trim()]);
}

test('组件样式不写死颜色，圆角只取 token', () => {
  const sheets = [
    new URL('../src/components/ui/kit.css', import.meta.url),
    new URL('../../legacy-web/ui-foundation.css', import.meta.url),
    new URL('../../legacy-web/pagination.css', import.meta.url),
    new URL('../src/console-shell.css', import.meta.url),
    new URL('../src/system-update.css', import.meta.url),
    new URL('../src/accounts.css', import.meta.url),
    new URL('../src/request-records.css', import.meta.url),
    new URL('../src/proxies.css', import.meta.url),
    new URL('../src/tokens.css', import.meta.url),
    new URL('../src/session-blocks.css', import.meta.url),
    new URL('../src/nodes.css', import.meta.url),
    new URL('../src/settings.css', import.meta.url),
    new URL('../src/theme-settings.css', import.meta.url),
  ];
  // 外壳组件、系统更新弹窗、账号页、请求 / 代理 / 令牌 / 会话封禁四页、节点管理、系统设置、主题设置及其子组件与组件库同样只取 token。
  const shell = ['Dashboard.vue', 'AppNavigation.vue', 'Login.vue', 'SystemUpdateDialog.vue', 'Accounts.vue', 'AgyAccountUsage.vue', 'AgyQuotaRow.vue', 'UsageWindowStats.vue', 'SchedulingDetails.vue', 'ProxyPicker.vue', 'PlatformBadge.vue', 'runtime/ExecutionNodeBadge.vue',
    'RequestDiagnostics.vue', 'NativeStageDetails.vue', 'AccountFilterSelect.vue', 'Proxies.vue', 'Tokens.vue', 'AccountScopePicker.vue', 'SessionPolicyBlocks.vue',
    'Nodes.vue', 'runtime/AccountNodeSelector.vue', 'runtime/AccountNodeMigration.vue', 'Settings.vue', 'ThemeSettings.vue', 'theme/ThemePreview.vue'].map(name => new URL(`../src/components/${name}`, import.meta.url));
  const problems = [];
  for (const file of [...sheets, ...shell, ...sourceFiles(uiRoot)]) {
    const text = readFileSync(file, 'utf8');
    const css = file.pathname.endsWith('.vue') ? [...text.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(match => match[1]).join('\n') : file.pathname.endsWith('.css') ? text : '';
    for (const [name, value] of declarations(css)) {
      // 颜色字面量只允许出现在主题 token 的定义处。
      if (!/^--ui-(?:color|shadow)-/.test(name) && colorLiteral.test(value)) problems.push(`${file.pathname}: ${name}: ${value}`);
      if (name === 'border-radius' && !value.includes('var(--ui-radius-') && !radiusLiteral.test(value)) problems.push(`${file.pathname}: ${name}: ${value}`);
    }
    const script = file.pathname.endsWith('.css') ? '' : text.replace(/<style[^>]*>[\s\S]*?<\/style>/g, '');
    if (/#[0-9a-fA-F]{6}\b|\brgba?\(/.test(script) || paletteUtility.test(script)) problems.push(`${file.pathname}: 模板或脚本含写死颜色`);
  }
  assert.deepEqual(problems, []);
});
