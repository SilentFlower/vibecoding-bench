/** 仅供本地回归，在退出时核对原fetch身份，不读取任何请求或配置。 */
const original = globalThis.fetch;
process.on('exit', () => process.stdout.write(JSON.stringify({type: 'audit_fetch_restored',
  restored: globalThis.fetch === original}) + '\n'));
await import('./host.mjs');
