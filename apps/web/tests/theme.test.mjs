import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import test from 'node:test';
import { contrast } from '../src/theme/color.ts';
import { DEFAULT_THEME_SEED, THEME_PRESETS, createTheme, parseThemeSeed } from '../src/theme/tokens.ts';
import { THEME_MODE_STORAGE_KEY, THEME_STORAGE_KEY, readStoredTheme, readThemeMode, resolveScheme, writeStoredTheme, writeThemeMode } from '../src/theme/runtime.ts';
import { THEME_SEED_KEYS, changedSeedKeys, normalizeHexInput, parseSeedNumber, presetIdOf } from '../src/theme/editor.ts';

const foundation = readFileSync(new URL('../../legacy-web/ui-foundation.css', import.meta.url), 'utf8');
const themable = /(--ui-(?:color|shadow|radius)-[a-z0-9-]+|--ui-(?:font-size-base|control-base|size-step|space-unit))\s*:\s*([^;]+);/g;
const normalize = value => value.trim().replace(/\s+/g, ' ');
const hexOf = (vars, name) => {
  assert.match(vars[name], /^#[0-9a-f]{6}$/, name);
  return vars[name];
};

/** 取出 ui-foundation.css 中指定选择器块的正文（块内没有嵌套花括号）。 */
const block = selector => {
  const start = foundation.indexOf(`${selector} {`);
  assert.ok(start >= 0, selector);
  return foundation.slice(foundation.indexOf('{', start) + 1, foundation.indexOf('}', start));
};
const themeVars = css => Object.fromEntries([...css.matchAll(themable)].map(([, name, value]) => [name, normalize(value)]));
const normalized = vars => Object.fromEntries(Object.entries(vars).map(([name, value]) => [name, normalize(value)]));
const lightBlock = block(':root');
const darkBlock = block(':root[data-ui-scheme=dark]');

test('默认主题与 ui-foundation.css 默认值逐项一致（双向）', () => {
  assert.deepEqual(themeVars(lightBlock), normalized(createTheme(DEFAULT_THEME_SEED)));
  assert.match(lightBlock, /color-scheme:\s*light;/);
});

test('深色默认主题与 ui-foundation.css 深色块逐项一致（双向，深色块只写与浅色不同的值）', () => {
  const dark = themeVars(darkBlock);
  assert.deepEqual({ ...themeVars(lightBlock), ...dark }, normalized(createTheme(DEFAULT_THEME_SEED, 'dark')));
  for (const [name, value] of Object.entries(dark)) assert.notEqual(value, themeVars(lightBlock)[name], `${name} 与浅色相同，不应重复写入`);
  assert.match(darkBlock, /color-scheme:\s*dark;/);
});

test('深色派生与确认稿 palette.js 逐值一致（六个预设与四个功能色）', () => {
  const source = readFileSync(new URL('../../../doc/design/console-v2/palette.js', import.meta.url), 'utf8');
  const palette = JSON.parse(source.slice(source.indexOf('{'), source.lastIndexOf('}') + 1));
  assert.deepEqual(palette.presets.map(preset => preset.seed), THEME_PRESETS.map(preset => preset.primary));
  for (const preset of palette.presets) {
    const vars = createTheme({ ...DEFAULT_THEME_SEED, primary: preset.seed }, 'dark');
    for (const [key, name] of [['base', ''], ['hover', '-hover'], ['container', '-container'], ['text', '-text'], ['ring', '-ring']]) {
      assert.equal(vars[`--ui-color-primary${name}`], preset[key], `${preset.id} ${key}`);
    }
    assert.equal(vars['--ui-color-on-primary'], preset.on, `${preset.id} on`);
  }
  for (const tone of palette.tones) {
    const vars = createTheme({ ...DEFAULT_THEME_SEED, [tone.id]: tone.seed }, 'dark');
    assert.deepEqual([vars[`--ui-color-${tone.id}`], vars[`--ui-color-${tone.id}-text`], vars[`--ui-color-${tone.id}-bg`]], [tone.base, tone.text, tone.bg], tone.id);
  }
});

test('深色下预设与边界色：按钮文字 ≥ 4.5、实色对卡片底 ≥ 3、派生文字 ≥ 5.5，中性正文 ≥ 4.5', () => {
  const colors = [...THEME_PRESETS.map(preset => preset.primary), '#ffee00', '#111111', '#000000', '#ff00ff', '#00ffff', '#808080', '#ffffff'];
  for (const color of colors) {
    for (const surface of ['default', 'soft']) {
      const vars = createTheme({ ...DEFAULT_THEME_SEED, primary: color, success: color, warning: color, danger: color, info: color, surface }, 'dark');
      const card = hexOf(vars, '--ui-color-surface');
      const primary = hexOf(vars, '--ui-color-primary');
      assert.ok(contrast(hexOf(vars, '--ui-color-on-primary'), primary) >= 4.5, `${color} 按钮文字`);
      assert.ok(contrast(primary, card) >= 3, `${color} 实色/卡片底`);
      for (const background of ['--ui-color-primary-container', '--ui-color-surface']) {
        assert.ok(contrast(hexOf(vars, '--ui-color-primary-text'), hexOf(vars, background)) >= 5.5, `${color} 主色文字/${background}`);
      }
      for (const tone of ['success', 'warning', 'danger', 'info']) {
        assert.ok(contrast(hexOf(vars, `--ui-color-${tone}`), card) >= 3, `${color} ${tone} 实色`);
        for (const background of [`--ui-color-${tone}-bg`, '--ui-color-surface']) {
          assert.ok(contrast(hexOf(vars, `--ui-color-${tone}-text`), hexOf(vars, background)) >= 5.5, `${color} ${tone}/${background}`);
        }
      }
      for (const [text, background] of [['text', 'surface'], ['text-2', 'surface'], ['text-3', 'surface'], ['text', 'layout'], ['text-3', 'layout'], ['text-3', 'fill-subtle'],
        ['neutral-text', 'neutral-bg'], ['cc-text', 'cc-bg'], ['agy-text', 'agy-bg'], ['feedback-text', 'feedback-surface'], ['ink-text', 'ink']]) {
        assert.ok(contrast(hexOf(vars, `--ui-color-${text}`), hexOf(vars, `--ui-color-${background}`)) >= 4.5, `${color} ${surface} ${text}/${background}`);
      }
    }
  }
});

test('新增 token：开关滑块随深浅变化，终端配色两种模式相同，深浅输出键集合一致', () => {
  const light = createTheme(DEFAULT_THEME_SEED);
  const dark = createTheme(DEFAULT_THEME_SEED, 'dark');
  assert.equal(light['--ui-color-knob'], '#ffffff');
  assert.equal(dark['--ui-color-knob'], '#eceef6');
  const terminal = ['fg', 'dim', 'cursor', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan'].map(name => `--ui-color-term-${name}`);
  assert.deepEqual(terminal.map(name => light[name]), ['#d9dbe8', '#8a8ea6', '#ed6ea7', '#f47174', '#4cd6a3', '#f7b94d', '#8fadf8', '#c3a6f5', '#5fd1d7']);
  assert.deepEqual(terminal.map(name => dark[name]), terminal.map(name => light[name]));
  // 终端文字在两种模式的墨底上都可读。
  for (const vars of [light, dark]) for (const name of terminal.filter(name => !name.endsWith('dim'))) assert.ok(contrast(vars[name], vars['--ui-color-ink']) >= 4.5, name);
  assert.deepEqual(Object.keys(dark).sort(), Object.keys(light).sort());
  assert.deepEqual(Object.keys(createTheme({ ...DEFAULT_THEME_SEED, surface: 'soft', primary: '#2f6bd8' }, 'dark')).sort(), Object.keys(light).sort());
});

test('主题模式：缺失、非法、读取抛错按跟随系统；保存跟随系统删除键；解析深浅', () => {
  const memory = new Map();
  const storage = { getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, value), removeItem: key => memory.delete(key) };
  assert.equal(THEME_MODE_STORAGE_KEY, 'flower2api.theme-mode');
  assert.equal(readThemeMode(storage), 'system');
  for (const raw of ['', 'Dark', 'auto', '{"mode":"dark"}', 'system ']) {
    memory.set(THEME_MODE_STORAGE_KEY, raw);
    assert.equal(readThemeMode(storage), 'system', raw);
  }
  for (const mode of ['light', 'dark']) {
    assert.equal(writeThemeMode(mode, storage), true);
    assert.equal(memory.get(THEME_MODE_STORAGE_KEY), mode);
    assert.equal(readThemeMode(storage), mode);
  }
  assert.equal(writeThemeMode('system', storage), true);
  assert.equal(memory.has(THEME_MODE_STORAGE_KEY), false);
  const broken = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); }, removeItem() { throw new Error('denied'); } };
  assert.equal(readThemeMode(broken), 'system');
  assert.equal(writeThemeMode('dark', broken), false);
  assert.equal(readThemeMode(undefined), 'system');
  assert.equal(writeThemeMode('dark', undefined), false);
  assert.deepEqual([['system', false], ['system', true], ['light', true], ['dark', false]].map(([mode, prefersDark]) => resolveScheme(mode, prefersDark)), ['light', 'dark', 'light', 'dark']);
});

test('首帧内联脚本：两份入口读取同一模式键并写 data-ui-scheme', () => {
  for (const path of ['../index.html', '../../legacy-web/index.html']) {
    const html = readFileSync(new URL(path, import.meta.url), 'utf8');
    const head = html.slice(0, html.indexOf('</head>'));
    const inline = [...head.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]).find(script => script.includes('uiScheme'));
    assert.ok(inline, `${path} 缺少首帧脚本`);
    assert.ok(inline.includes(`'${THEME_MODE_STORAGE_KEY}'`), `${path} 模式键`);
    assert.ok(inline.includes('prefers-color-scheme: dark'), `${path} 系统偏好`);
    // 首帧脚本必须在任何样式表与模块脚本之前执行。
    assert.ok(head.indexOf(inline) < Math.min(...['<link rel="stylesheet"', '<script type="module"', '<script src'].map(tag => head.indexOf(tag)).filter(index => index >= 0), Infinity), `${path} 脚本顺序`);
    assert.doesNotMatch(html, /dataset\.theme\s*=/, `${path} 仍写死 data-theme`);
  }
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

// 原生任务页与独立 /runtime/ 文档共用的样式（ui-foundation.css、pagination.css 另列）。
const legacySheets = ['style.css', 'environments.css', 'console.css', 'approved-design.css', 'work-design.css', 'environment-design.css', 'capture-workspace.css']
  .map(name => new URL(`../../legacy-web/${name}`, import.meta.url));

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
    new URL('../src/native-environment.css', import.meta.url),
    // 旧层与全局排版：shadcn 变量改指第二版 token，全仓颜色字面量只剩 token 定义处。
    new URL('../src/style.css', import.meta.url),
    new URL('../src/approved-design.css', import.meta.url),
    ...legacySheets,
  ];
  // 外壳组件、系统更新弹窗、账号页、请求 / 代理 / 令牌 / 会话封禁四页、节点管理、系统设置、主题设置、任务与工程宿主、运行环境及其子组件与组件库同样只取 token。
  const shell = ['Dashboard.vue', 'AppNavigation.vue', 'Login.vue', 'SystemUpdateDialog.vue', 'Accounts.vue', 'AgyAccountUsage.vue', 'AgyQuotaRow.vue', 'UsageWindowStats.vue', 'SchedulingDetails.vue', 'ProxyPicker.vue', 'PlatformBadge.vue', 'runtime/ExecutionNodeBadge.vue',
    'RequestDiagnostics.vue', 'NativeStageDetails.vue', 'AccountFilterSelect.vue', 'Proxies.vue', 'Tokens.vue', 'AccountScopePicker.vue', 'SessionPolicyBlocks.vue',
    'Nodes.vue', 'runtime/AccountNodeSelector.vue', 'runtime/AccountNodeMigration.vue', 'Settings.vue', 'ThemeSettings.vue', 'theme/ThemePreview.vue',
    'TasksWorkspace.vue', 'RuntimeEnvironments.vue', 'runtime/CaptureWorkspace.vue', 'runtime/RunDetails.vue', 'runtime/TaskProxyDialog.vue', 'runtime/EnvironmentResources.vue', 'runtime/EnvironmentKernel.vue', 'runtime/RunWindowForm.vue'].map(name => new URL(`../src/components/${name}`, import.meta.url));
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

test('原生样式不再定义旧变量，只引用第二版 token', () => {
  // 旧变量（--ink、--line、--muted、--border 等）挂在原生作用域根上会被内嵌的 Vue 组件继承，迁移后一律删除。
  const problems = [...legacySheets, new URL('../src/native-environment.css', import.meta.url)].flatMap(file => declarations(readFileSync(file, 'utf8'))
    .filter(([name]) => name.startsWith('--') && !name.startsWith('--ui-'))
    .map(([name]) => `${file.pathname}: ${name}`));
  assert.deepEqual(problems, []);
});

test('旧层已删除：旧变量名、shadcn 色名工具类与 lucide 图标不再出现', () => {
  // 删除 @theme 色名映射后，残留的 bg-background 等工具类不会报错，只是静默不生成样式，所以必须静态拦截。
  const oldVariable = /(?<![\w-])--(?:background|foreground|card|card-foreground|popover|popover-foreground|primary|primary-foreground|secondary|secondary-foreground|muted|muted-foreground|accent|accent-foreground|destructive|border|input|ring|radius|font-body|body-font|ui-font|ui-accent|ui-border|ui-text|ui-surface|ui-font-(?:small|body|card|heading|page)|ui-control-(?:height|compact|space))(?![\w-])/;
  // fill / stroke 前缀不列入：第二版 token 自身有 fill-muted 等键名。
  const oldUtility = /(?<![\w-])(?:bg|text|border|ring|outline|divide|placeholder|from|via|to|shadow|caret|accent|decoration)-(?:background|foreground|card|popover|primary|secondary|muted|accent|destructive|border|input|ring)(?:-foreground)?(?:\/\d+)?(?![\w-])/;
  const legacyFiles = readdirSync(new URL('../../legacy-web/', import.meta.url)).filter(name => /\.(?:css|js|html)$/.test(name))
    .map(name => new URL(`../../legacy-web/${name}`, import.meta.url));
  const files = [...sourceFiles(new URL('../src/', import.meta.url)), new URL('../index.html', import.meta.url), new URL('../ui-preview.html', import.meta.url), ...legacyFiles];
  const problems = [];
  for (const file of files) {
    const lines = readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, index) => {
      const where = `${file.pathname}:${index + 1}`;
      if (oldVariable.test(line)) problems.push(`${where} 旧变量 ${line.match(oldVariable)[0]}`);
      if (oldUtility.test(line)) problems.push(`${where} 旧工具类 ${line.match(oldUtility)[0]}`);
      if (line.includes('lucide-vue-next')) problems.push(`${where} lucide 图标`);
    });
  }
  const manifest = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
  if ('lucide-vue-next' in { ...manifest.dependencies, ...manifest.devDependencies }) problems.push('package.json 仍依赖 lucide-vue-next');
  assert.deepEqual(problems, []);
});

test('原生页与 Vue 的图标 sprite 保持同一份内容', () => {
  const legacy = readFileSync(new URL('../../legacy-web/approved-icons.svg', import.meta.url), 'utf8');
  const vue = readFileSync(new URL('../src/assets/approved-icons.svg', import.meta.url), 'utf8');
  assert.equal(legacy, vue);
});
