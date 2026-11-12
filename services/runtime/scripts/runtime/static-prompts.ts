import { createHash } from 'node:crypto';
import ts from 'typescript';

/** 已审查的工厂及逐次读取；表达式仅来自固定构建规则。 */
export interface StaticTextRule {
  sha256: string;
  reads: { call: string; value: string }[];
  key: string[];
}

const RULES_293: Record<string, StaticTextRule> = {
  KLo: { sha256: 'd790705362b02031f254d97110965681dae9051d6c7c299c16c5fed7439b82eb', reads: [{ call: 'RVt()', value: 'e===null?RVt():false' }], key: ['e===null', '__ccrb_static_dep0'] },
  XLo: { sha256: 'ea70b40201e6da803b11a167e7a9370b1313191af38d2151eecce8833e260999', reads: [{ call: 'AVt(e,"standard")', value: 'AVt(e,"standard")' }, { call: 'bR()', value: 'bR()' }], key: ['__ccrb_static_dep0', '__ccrb_static_dep1'] },
  QLo: { sha256: '3f00445ae344c05c6e03c271c251950e193c006c231141db74c1874a0d2878e2', reads: [{ call: 'T("tengu_verified_vs_assumed",!1)', value: 'T("tengu_verified_vs_assumed",!1)' }], key: ['__ccrb_static_dep0'] },
  nNo: { sha256: '1d6ee7f52499737d1a65e961b56145128f1f14a4fa39b6464693178bc8635d62', reads: [{ call: 'CN()', value: 'CN()' }, { call: 'HE()', value: '__ccrb_static_dep0?false:HE()' }], key: ['__ccrb_static_dep0', '__ccrb_static_dep1', 'e.has(jE)', 'e.has(RR)', 'e.has($e)'] },
  sNo: { sha256: 'e8befa3c92a6792ccc9ff59370f37145b6c7ae39d690b2d8aec5e921e191b38a', reads: [], key: [] },
  pNo: { sha256: '5b987a317f790ee6a06744334dc20c520b1dd622d6b5d94bfde1832d4d57824d', reads: [{ call: 'TLo()', value: 'TLo()' }], key: ['e', '__ccrb_static_dep0'] },
};
const HELPERS_293: Record<string, string> = {
  kg: '7196b9a05100e0d7bbdf606edf55849e932dad0031806b01681a279a3e651e0a',
  $Lo: 'ffa181b5a10e6fc257368d7036e983cb8f8be8efb749b8420ed759e733b2c0cf',
};

/** 固定正文转换与构建审计；不携带专有正文。 */
export interface StaticTextRewrite {
  changes: { start: number; end: number; text: string }[];
  bodies: ts.Block[];
  declarations: string[];
  audit: { factory: string; source_sha256: string; key_reads: string[]; key_conditions: string[]; cache_slots: number; cache_bytes_limit: number }[];
}

/** 为已核验的纯文本工厂加入缓存，保留条件读取和外层原生钩子。
 * @param tree 当前固定原生模块的语法树。
 * @param rules 可信构建规则；默认只接受已经审查的固定 293 函数。
 * @param helpers 纯辅助函数的固定摘要。
 * @return 可合并到既有构建变换的替换、排除节点和审计记录。
 */
export function rewriteStaticText(tree: ts.SourceFile, rules: Record<string, StaticTextRule> = RULES_293, helpers: Record<string, string> = HELPERS_293): StaticTextRewrite {
  if (tree.text.includes('__ccrb_static_')) throw new Error('静态正文构建绑定名称冲突');
  const functions = new Map(tree.statements.filter(ts.isFunctionDeclaration).filter(node => node.name).map(node => [node.name!.text, node]));
  for (const [name, sha256] of Object.entries(helpers)) {
    const node = functions.get(name);
    if (!node || createHash('sha256').update(node.getText(tree)).digest('hex') !== sha256) throw new Error('固定静态正文辅助函数不匹配：' + name);
  }
  const result: StaticTextRewrite = { changes: [], bodies: [], declarations: [], audit: [] };
  for (const [name, rule] of Object.entries(rules)) {
    const node = functions.get(name);
    if (!node?.body || node.asteriskToken || node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.AsyncKeyword) || createHash('sha256').update(node.getText(tree)).digest('hex') !== rule.sha256) throw new Error('固定静态正文工厂不匹配：' + name);
    const start = node.body.getStart(tree), end = node.body.getEnd();
    const replacements: { start: number; end: number; text: string }[] = [];
    for (const [index, read] of rule.reads.entries()) {
      const calls: ts.CallExpression[] = [];
      const visit = (child: ts.Node): void => {
        if (ts.isCallExpression(child) && child.getText(tree) === read.call) calls.push(child);
        ts.forEachChild(child, visit);
      };
      visit(node.body);
      if (calls.length !== 1) throw new Error('固定静态正文条件读取不匹配：' + name);
      replacements.push({ start: calls[0]!.getStart(tree) - start, end: calls[0]!.getEnd() - start, text: '__ccrb_static_dep' + index });
    }
    let body = node.body.getText(tree);
    for (const change of replacements.sort((a, b) => b.start - a.start)) body = body.slice(0, change.start) + change.text + body.slice(change.end);
    // 只缓存纯格式化结果；条件读取仍逐次求值，外层段落钩子和原生失效处理不受影响。
    const reads = rule.reads.map((read, index) => 'const __ccrb_static_dep' + index + '=(' + read.value + ');').join('');
    const slot = '__ccrb_static_' + name;
    const keys = rule.key.map((value, index) => ({ current: '__ccrb_static_key' + index, stored: slot + '_key' + index, value }));
    result.declarations.push('let ' + [slot + '_text', ...keys.map(key => key.stored)].join(',') + ';');
    const keyReads = keys.map(key => 'const ' + key.current + '=(' + key.value + ');').join('');
    const hit = [slot + '_text!==undefined', ...keys.map(key => key.current + '===' + key.stored)].join('&&');
    const store = keys.map(key => key.stored + '=' + key.current + ';').join('') + slot + '_text=__ccrb_static_value;';
    // 命中时只比较原始条件；编码预算检查与格式化闭包都留在未命中分支。
    result.changes.push({ start, end, text: '{' + reads + keyReads + 'if(' + hit + ')return ' + slot + '_text;const __ccrb_static_value=(()=>'+ body + ')();if(__ccrb_static_fits(__ccrb_static_value,[' + keys.map(key => key.current).join(',') + '])){' + store + '}return __ccrb_static_value;}' });
    result.bodies.push(node.body);
    result.audit.push({ factory: name, source_sha256: rule.sha256, key_reads: rule.reads.map(read => read.value), key_conditions: rule.key, cache_slots: 1, cache_bytes_limit: 64 * 1024 });
  }
  return result;
}
