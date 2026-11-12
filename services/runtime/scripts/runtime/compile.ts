import { mkdir, readFile, stat, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, resolve, sep } from 'node:path';
import ts from 'typescript';
import { NATIVE_EXPORTS_293, PROFILE_293 } from '../../src/runtime/293/source-profile';
import { rewriteStaticText } from './static-prompts';
import type { StaticTextRewrite } from './static-prompts';

const root = process.env.CCRB_BUILD_ROOT!;
const source = process.env.CCRB_BUILD_SOURCE!;
const project = process.env.CCRB_BUILD_PROJECT!;
const modules = resolve(root, 'modules');
const manifest: { name: string; sha256: string }[] = JSON.parse(await readFile(resolve(root, 'modules.json'), 'utf8'));
const sourceHashes = new Map(manifest.map(row => [row.name, row.sha256]));
const rewrites: { file: string; start: number; end: number; kind: string; specifier: string }[] = [];
const dynamic: { file: string; start: number; kind: string }[] = [];
const nativeImports: { file: string; start: number; specifier: string }[] = [];
const executionGuards: { file: string; start: number; end: number; factory: string; kind: string }[] = [];
const staticTextGenerators: StaticTextRewrite['audit'] = [];
const terminalAddons = new Map([
  ['/$bunfs/root/chunk-y8bhqk9z.js', '/$bunfs/root/audio-capture.node'],
  ['/$bunfs/root/chunk-2jb0trbw.js', '/$bunfs/root/clipboard-napi.node'],
]);
const plainResources = new Map<string, Promise<string>>();
const resourceTranscodes: { file: string; source_sha256: string; plain_sha256: string; source_bytes: number; plain_bytes: number }[] = [];
const nativeModules = new Set(['child_process', 'bun:ffi', 'perf_hooks', 'fs', 'path', 'stream', 'constants', 'util', 'assert', 'events', 'http', 'https', 'net', 'tls', 'url', 'http2', 'crypto', 'undici', 'os', 'tty', 'process', 'buffer', 'fs/promises', 'querystring', 'zlib', 'dns']);
const mappings = new Set<string>();
const definitions = Object.entries(PROFILE_293.modules).map(([role, file]) => [role, file, NATIVE_EXPORTS_293[role as keyof typeof NATIVE_EXPORTS_293]] as const);
const entry = definitions.map(([, file, symbols]) => 'import {' + symbols.join(',') + '} from ' + JSON.stringify(file) + ';').join('\n') +
  '\nimport {reportStartupFailure,startWorker} from ' + JSON.stringify(resolve(project, 'src/runtime/293/worker.ts')) + ';\n' +
  'try { await startWorker({' + definitions.map(([role, , symbols]) => role + ':{' + symbols.join(',') + '}').join(',') + '}); process.exit(0); } catch (error) { await reportStartupFailure(error); process.exit(111); }\n';
await writeFile(resolve(root, 'entry.mjs'), entry);

try {
  const result = await Bun.build({
    entrypoints: [resolve(root, 'entry.mjs')], target: 'bun', format: 'esm', env: 'disable', metafile: true,
    loader: { '.txt': 'text', '.md': 'text' },
    minify: { whitespace: true, syntax: true, identifiers: true, keepNames: true },
    plugins: [{ name: 'fixed-293-closure', setup(builder) {
      builder.onResolve({ filter: /^\/\$bunfs\/root\// }, async ({ path }) => {
        if (!sourceHashes.has(path)) throw new Error('原生依赖不在固定提取清单中');
        const mapped = resolve(modules, path.slice('/$bunfs/root/'.length));
        if (!mapped.startsWith(modules + sep)) throw new Error('原生模块路径越界');
        mappings.add(path);
        if (path.endsWith('.zst')) {
          let resource = plainResources.get(path);
          if (!resource) {
            resource = (async () => {
              const bytes = await readFile(mapped);
              const sourceSha256 = createHash('sha256').update(bytes).digest('hex');
              if (sourceSha256 !== sourceHashes.get(path)) throw new Error('压缩资源不在固定提取清单中');
              const plain = Buffer.from(Bun.zstdDecompressSync(bytes));
              new TextDecoder('utf-8', { fatal: true }).decode(plain);
              // 官方资源读取器按魔数识别压缩，也接受原文；让外层归档统一压缩，保留完整内容。
              const target = resolve(root, 'resources', path.slice('/$bunfs/root/'.length));
              if (!target.startsWith(resolve(root, 'resources') + sep)) throw new Error('资源转换路径越界');
              await mkdir(dirname(target), { recursive: true });
              await writeFile(target, plain);
              resourceTranscodes.push({ file: path, source_sha256: sourceSha256, plain_sha256: createHash('sha256').update(plain).digest('hex'), source_bytes: bytes.length, plain_bytes: plain.length });
              return target;
            })();
            plainResources.set(path, resource);
          }
          return { path: await resource };
        }
        return { path: mapped };
      });
      builder.onLoad({ filter: /modules\/.*\.js$/ }, async ({ path }) => {
        const bytes = await readFile(path);
        const file = '/$bunfs/root/' + path.slice(modules.length + 1);
        if (createHash('sha256').update(bytes).digest('hex') !== sourceHashes.get(file)) throw new Error('提取模块在构建期间改变');
        const text = bytes.toString('utf8');
        if (!text.includes('import.meta.require') && !text.includes('He(') && !text.includes('.zst') && !text.includes(PROFILE_293.modules.permissions) && !text.includes('"local"') && !text.includes('"local-jsx"')) return { contents: text, loader: 'js' };
        // 只改真实语法节点，避免把内嵌示例、模板文本或普通字符串误当作依赖表达式。
        const tree = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
        const aliases = new Set<string>();
        const toolFactories = new Set<string>();
        for (const node of tree.statements) {
          if (!ts.isImportDeclaration(node) || !ts.isStringLiteral(node.moduleSpecifier)) continue;
          const bindings = node.importClause?.namedBindings;
          if (bindings && ts.isNamedImports(bindings)) for (const element of bindings.elements) {
            if (node.moduleSpecifier.text === '/$bunfs/root/chunk-0y12vz6b.js' && (element.propertyName ?? element.name).text === 'He') aliases.add(element.name.text);
            if (node.moduleSpecifier.text === PROFILE_293.modules.permissions && (element.propertyName ?? element.name).text === 'Vt') toolFactories.add(element.name.text);
          }
        }
        const changes: { start: number; end: number; text: string }[] = [];
        const imports: string[] = [];
        const excludedBodies = new Set<ts.Node>();
        if (file === PROFILE_293.modules.core) {
          const staticText = rewriteStaticText(tree);
          changes.push(...staticText.changes);
          staticText.bodies.forEach(body => excludedBodies.add(body));
          staticTextGenerators.push(...staticText.audit);
          imports.push('import {staticTextFits as __ccrb_static_fits} from ' + JSON.stringify(resolve(project, 'src/runtime/293/static-text.ts')) + ';', ...staticText.declarations);
        }
        const visit = (node: ts.Node): void => {
          if (excludedBodies.has(node)) return;
          if (ts.isCallExpression(node)) {
            const callee = node.expression;
            // 已核对的 Vt.create 只进入本地执行链；顶层限制同时排除同名局部变量遮蔽。
            // 保留工具声明的全部原生生成逻辑，让打包器移除已无法触达的执行依赖。
            const declaration = node.parent;
            const definition = node.arguments[0];
            if (ts.isIdentifier(callee) && toolFactories.has(callee.text) && node.arguments.length === 1 && definition && ts.isObjectLiteralExpression(definition) &&
              ts.isVariableDeclaration(declaration) && declaration.initializer === node && ts.isVariableDeclarationList(declaration.parent) && ts.isVariableStatement(declaration.parent.parent) && ts.isSourceFile(declaration.parent.parent.parent)) {
              const create = definition.properties.find(property => property.name && ts.isIdentifier(property.name) && property.name.text === 'create');
              const hasName = definition.properties.some(property => property.name && ts.isIdentifier(property.name) && property.name.text === 'name');
              if (hasName && create && ts.isMethodDeclaration(create) && create.body) {
                const start = create.body.getStart(tree), end = create.body.getEnd();
                changes.push({ start, end, text: '{throw new Error("单轮桥接禁止执行本地工具");}' });
                executionGuards.push({ file, start, end, factory: callee.text, kind: 'tool-create' });
                excludedBodies.add(create.body);
              }
            }
            const direct = ts.isPropertyAccessExpression(callee) && callee.name.text === 'require' && ts.isMetaProperty(callee.expression) && callee.expression.keywordToken === ts.SyntaxKind.ImportKeyword;
            const alias = ts.isIdentifier(callee) && aliases.has(callee.text);
            if (direct || alias) {
              const first = node.arguments[0];
              if (alias && node.arguments.length === 1 && first && ts.isStringLiteral(first) && terminalAddons.get(file) === first.text) {
                const start = node.getStart(tree), end = node.getEnd();
                changes.push({ start, end, text: '(()=>{throw new Error("单轮 API 不提供终端剪贴板或音频输入");})()' });
                executionGuards.push({ file, start, end, factory: first.text, kind: 'terminal-addon-load' });
                return;
              }
              if (node.arguments.length === 1 && first && ts.isStringLiteral(first) && first.text.startsWith('/$bunfs/root/')) {
                if (first.text.endsWith('.zst')) throw new Error('压缩资源不能作为普通 require 处理');
                const start = node.getStart(tree), end = node.getEnd();
                changes.push({ start, end, text: 'require(' + JSON.stringify(first.text) + ')' });
                rewrites.push({ file, start, end, kind: alias ? 'helper-require' : 'static-require', specifier: first.text });
                return;
              }
              if (first && ts.isStringLiteral(first)) {
                if (!nativeModules.has(first.text)) throw new Error('固定闭包出现未登记的外部依赖');
                nativeImports.push({ file, start: node.getStart(tree), specifier: first.text });
              } else dynamic.push({ file, start: node.getStart(tree), kind: direct ? 'dynamic-require' : 'helper-dynamic-require' });
            }
          }
          if (ts.isStringLiteral(node) && node.text.startsWith('/$bunfs/root/') && node.text.endsWith('.zst')) {
            const binding = '__ccrb_resource_' + imports.length;
            if (text.includes(binding)) throw new Error('资源绑定名称冲突');
            const start = node.getStart(tree), end = node.getEnd();
            imports.push('import ' + binding + ' from ' + JSON.stringify(node.text) + ' with {type:"file"};');
            changes.push({ start, end, text: binding });
            rewrites.push({ file, start, end, kind: 'embedded-file', specifier: node.text });
            return;
          }
          ts.forEachChild(node, visit);
        };
        for (const statement of tree.statements) {
          if (!ts.isVariableStatement(statement)) continue;
          for (const definition of statement.declarationList.declarations) {
            if (!definition.initializer || !ts.isObjectLiteralExpression(definition.initializer)) continue;
            const properties = new Map(definition.initializer.properties.filter(property => property.name && (ts.isIdentifier(property.name) || ts.isStringLiteral(property.name))).map(property => [(property.name as ts.Identifier | ts.StringLiteral).text, property]));
            const type = properties.get('type');
            if (!type || !ts.isPropertyAssignment(type) || !ts.isStringLiteral(type.initializer) || !['local', 'local-jsx'].includes(type.initializer.text) || !properties.has('name') || !properties.has('description')) continue;
            // local/local-jsx 的 load/call 仅进入终端本地执行；保留声明及全部可用性判断。
            // prompt 技能和未知对象继续保持原文，不能为了体积删除参与模型请求的说明。
            for (const name of ['load', 'call']) {
              const member = properties.get(name);
              if (!member) continue;
              const target = ts.isMethodDeclaration(member) ? member.body : ts.isPropertyAssignment(member) && (ts.isArrowFunction(member.initializer) || ts.isFunctionExpression(member.initializer)) ? member.initializer : undefined;
              if (!target) continue;
              const start = target.getStart(tree), end = target.getEnd();
              changes.push({ start, end, text: ts.isMethodDeclaration(member) ? '{throw new Error("单轮桥接禁止执行终端本地命令");}' : 'async()=>{throw new Error("单轮桥接禁止执行终端本地命令");}' });
              executionGuards.push({ file, start, end, factory: definition.name.getText(tree), kind: 'terminal-command-' + name });
              excludedBodies.add(target);
            }
          }
        }
        visit(tree);
        changes.sort((a, b) => b.start - a.start);
        let contents = text;
        let boundary = text.length;
        for (const change of changes) {
          if (change.end > boundary) throw new Error('依赖转换位置重叠');
          contents = contents.slice(0, change.start) + change.text + contents.slice(change.end);
          boundary = change.start;
        }
        return { contents: imports.join('\n') + '\n' + contents, loader: 'js' };
      });
    } }],
    compile: { executablePath: source, outfile: resolve(root, 'ccrb-worker'), autoloadDotenv: false, autoloadBunfig: false, autoloadTsconfig: false, autoloadPackageJson: false },
  });
  if (!result.success) throw new Error('固定源码构建失败，诊断数量=' + result.logs.length);
  await writeFile(resolve(root, 'closure.json'), JSON.stringify({ bun_version: Bun.version, bun_revision: Bun.revision, mapped_modules: [...mappings].sort(), rewrites, tool_execution_guards: executionGuards, static_text_generators: staticTextGenerators, resource_transcodes: resourceTranscodes.sort((a, b) => a.file.localeCompare(b.file)), native_imports: nativeImports, remaining_dynamic_calls: dynamic, actual_file_bytes: (await stat(resolve(root, 'ccrb-worker'))).size }, null, 2));
  process.exit(0);
} catch {
  process.stderr.write('固定 293 依赖转换或原生构建失败\n');
  process.exit(111);
}
