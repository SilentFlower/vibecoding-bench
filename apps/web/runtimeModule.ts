import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import postcss from 'postcss';
import selectorParser from 'postcss-selector-parser';
import type { Plugin } from 'vite';

const directory = fileURLToPath(new URL('../legacy-web/', import.meta.url));
const scripts = ['ui-controls.js', 'projects.js', 'environments.js', 'app.js'];
const styles = ['style.css', 'environments.css', 'console.css', 'approved-design.css', 'work-design.css', 'environment-design.css', 'capture-workspace.css', 'pagination.css'];

/** 将原页面选择器限制在原生任务根内，保留关键帧及字体资源语义。@param source 原CSS。@return 隔离样式。 */
function scopedStyles(source: string): string {
  const root = postcss.parse(source);
  root.walkAtRules('font-face', rule => { rule.remove(); });
  root.walkRules(rule => {
    if (rule.parent?.type === 'atrule' && /keyframes$/.test(rule.parent.name)) return;
    rule.selector = selectorParser(selectors => {
      selectors.each(selector => {
        selector.walkTags(node => { if (node.value === 'html' || node.value === 'body') node.replaceWith(selectorParser.className({value:node.value === 'html' ? 'task-runtime' : 'runtime-body'})); });
        selector.walkPseudos(node => { if (node.value === ':root') node.replaceWith(selectorParser.className({value:'task-runtime'})); });
        let rooted = false;
        selector.walkClasses(node => { if (node.value === 'task-runtime') rooted = true; });
        if (rooted) return;
        const first = selector.first;
        const sameRoot = first?.type === 'class' && first.value === 'console-design';
        // 逗号分组后的前导空格属于序列化格式，不能把同一根类变成后代选择器。
        if (sameRoot && first) first.spaces.before = '';
        if (!sameRoot) selector.prepend(selectorParser.combinator({value:' '}));
        selector.prepend(selectorParser.className({value:'task-runtime'}));
      });
    }).processSync(rule.selector);
  });
  return root.toString().replace(/url\((['"]?)(?!data:|https?:|\/|#)([^)'"\s]+)\1\)/g, 'url($1/runtime/$2$1)');
}

/** 构建时把单份运行控制器编译为ES模块；浏览器无需拉取HTML或执行脚本字符串。@return Vite插件。 */
export function runtimeModule(): Plugin {
  const identity = '\0virtual:task-runtime';
  const styleIdentity = '\0virtual:task-runtime-style.css';
  return {
    name: 'flower-task-runtime',
    resolveId(id) { return id === 'virtual:task-runtime' ? identity : id === 'virtual:task-runtime-style.css' ? styleIdentity : undefined; },
    load(id) {
      if (id === styleIdentity) { for (const file of styles) this.addWatchFile(directory + file);return styles.map(file => scopedStyles(readFileSync(directory + file, 'utf8'))).join('\n'); }
      if (id !== identity) return;
      for (const file of [...scripts, ...styles, 'index.html']) this.addWatchFile(directory + file);
      const html = readFileSync(directory + 'index.html', 'utf8').split('<body class="work-console">')[1]?.split('</body>')[0];
      if (!html) throw new Error('任务模板入口未找到');
      const template = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '').replaceAll('href="approved-icons.svg#', 'href="/runtime/approved-icons.svg#');
      const code = scripts.map(file => readFileSync(directory + file, 'utf8').replaceAll('href="approved-icons.svg#', 'href="/runtime/approved-icons.svg#')).join('\n');
      return `export const template=${JSON.stringify(template)};
/** 挂载独立执行控制器。@param scope 宿主浏览器接口。@return 清理函数。 */
export function mount(scope){
 const {document,window,location,history,fetch,EventSource,WebSocket,MutationObserver,ResizeObserver,setTimeout,clearTimeout,setInterval,clearInterval,requestAnimationFrame,cancelAnimationFrame,Terminal,FitAddon}=scope;
 ${code}
 return {dispose(){state.viewGeneration++;endRunDetail();leaveEnvironments();window.ProjectsUI.unmount();state.runsEventSource?.close();state.accLogin?.connection?.dispose();state.accLogin?.term?.dispose();state.continueRun?.term?.dispose();state.accLogin=null;state.continueRun=null;}};
}`;
    },
  };
}
