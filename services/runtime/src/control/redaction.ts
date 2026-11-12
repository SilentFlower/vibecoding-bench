import type { HeaderPair } from '../shared/contracts';
import { isObject } from '../shared/errors';

const SECRET_FIELD = /authorization|cookie|api[-_]?key|token|secret|password|credential/i;

/** 日志脱敏器，收集本次请求已知秘密并处理跨片段完成后的正文。 */
export class Redactor {
  private readonly secrets = new Set<string>();

  /** 注册一个完整输入中的秘密，原对象不会改变。
   * @param value 请求、配置或头部。
   * @return 无。
   */
  register(value: unknown): void {
    if (Array.isArray(value)) {
      for (const item of value) {
        if (Array.isArray(item) && typeof item[0] === 'string' && typeof item[1] === 'string' && SECRET_FIELD.test(item[0])) this.add(item[1]);
        else this.register(item);
      }
    } else if (isObject(value)) {
      for (const [key, child] of Object.entries(value)) {
        if (SECRET_FIELD.test(key) && typeof child === 'string') this.add(child);
        else this.register(child);
      }
    } else if (typeof value === 'string' && /^[a-z][a-z0-9+.-]*:\/\//i.test(value)) {
      try {
        const url = new URL(value);
        if (url.password) { this.add(url.password); this.add(decodeURIComponent(url.password)); }
      } catch {}
    }
  }

  private add(value: string): void {
    if (value.length >= 4) this.secrets.add(value);
    const bearer = /^Bearer\s+(.+)$/i.exec(value);
    if (bearer?.[1] && bearer[1].length >= 4) this.secrets.add(bearer[1]);
  }

  /** 脱敏普通文本，同时处理常见原生凭据及代理 URL。
   * @param value 原始文本。
   * @return 可存储的脱敏文本。
   */
  text(value: string): string {
    let result = value;
    for (const secret of [...this.secrets].sort((a, b) => b.length - a.length)) result = result.split(secret).join('[REDACTED]');
    return result
      .replace(/\bsk-ant-[A-Za-z0-9_-]+/g, '[REDACTED]')
      // 从固定分隔符开始匹配，避免长提示词中的普通单词反复尝试协议名。
      .replace(/:\/\/[^\s/:]+:[^\s/@]+@/g, '://[REDACTED]@')
      .replace(/("(?:access_token|refresh_token|api_key|password|secret)"\s*:\s*")[^"]*"/gi, '$1[REDACTED]"');
  }

  /** 对日志预览脱敏并按完整 UTF-8 字符截断。
   * @param value 完整文本或已经按字节保留的响应前缀。
   * @param maxBytes 脱敏后允许保存的最大字节数。
   * @param incomplete 是否只有原始数据前缀。
   * @return 可保存文本及是否发生截断。
   */
  preview(value: string, maxBytes: number, incomplete = false): { text: string; truncated: boolean } {
    // 响应可能恰好截在凭据中间，先省略末尾的秘密长度，避免残留部分凭据。
    let guard = 0;
    if (incomplete) for (const secret of this.secrets) guard = Math.max(guard, secret.length);
    const safe = this.text(guard ? value.slice(0, Math.max(0, value.length - guard)) : value);
    const bytes = Buffer.from(safe);
    return { text: new TextDecoder().decode(bytes.subarray(0, maxBytes), { stream: bytes.length > maxBytes }), truncated: incomplete || bytes.length > maxBytes };
  }

  /** 脱敏头部并保留字段顺序。
   * @param headers 原始有序头。
   * @return 不包含凭据的头部。
   */
  headers(headers: HeaderPair[]): HeaderPair[] {
    this.register(headers);
    return headers.map(([name, value]) => [this.text(name), SECRET_FIELD.test(name) ? '[REDACTED]' : this.text(value)]);
  }

  /** 深度脱敏 JSON，不修改参与发送的对象。
   * @param value 原始 JSON。
   * @return 可展示的 JSON。
   */
  value(value: unknown): unknown {
    if (typeof value === 'string') return this.text(value);
    if (Array.isArray(value)) return value.map(x => this.value(x));
    if (isObject(value)) return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, SECRET_FIELD.test(key) ? '[REDACTED]' : this.value(child)]));
    return value;
  }
}
