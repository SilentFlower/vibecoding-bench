import { describe, expect, test } from 'bun:test';
import { Redactor } from '../../src/control/redaction';

describe('持久日志的脱敏与字节边界', () => {
  test('完整输入先脱敏再截断，不产生半个 UTF-8 字符', () => {
    const redactor = new Redactor();
    redactor.register({ api_key: 'private-boundary-secret' });
    const result = redactor.preview('private-boundary-secret' + '汉字'.repeat(20), 13);
    expect(result.text).toBe('[REDACTED]汉');
    expect(Buffer.byteLength(result.text)).toBeLessThanOrEqual(13);
    expect(result.text).not.toContain('\ufffd');
    expect(result.truncated).toBe(true);
  });
  test('响应前缀截在凭据中间时不保存残余片段', () => {
    const redactor = new Redactor();
    redactor.register({ api_key: 'private-boundary-secret' });
    const result = redactor.preview('输出'.repeat(20) + 'private-bound', 1024, true);
    expect(result.text).not.toContain('private');
    expect(result.truncated).toBe(true);
  });
  test('配置秘密、Bearer、代理密码和重复头各自脱敏', () => {
    const redactor = new Redactor();
    const headers: [string, string][] = [['Authorization', 'Bearer fixture-token'], ['x-custom', 'fixture-token']];
    expect(redactor.headers(headers)).toEqual([['Authorization', '[REDACTED]'], ['x-custom', '[REDACTED]']]);
    expect(redactor.text('https://proxy:password@example.invalid')).toBe('https://[REDACTED]@example.invalid');
    expect(headers[0]![1]).toBe('Bearer fixture-token');
    redactor.register({ proxy_url: 'socks5://fixture:proxy-password@example.invalid' });
    expect(redactor.text('连接失败：proxy-password')).not.toContain('proxy-password');
    expect(redactor.text('HTTP://proxy:other-password@example.invalid')).toBe('HTTP://[REDACTED]@example.invalid');
  });
  test('长正文内的不同协议凭据全部脱敏，保留无凭据 URL 和业务文本', () => {
    const redactor = new Redactor();
    const prefix = '普通说明 abcdefghijklmnopqrstuvwxyz '.repeat(3000);
    const value = prefix + ' https://public.invalid/a socks5://user:first-secret@proxy.invalid HTTP://other:second-secret@other.invalid custom+scheme://name:third-secret@host.invalid';
    expect(redactor.text(value)).toBe(prefix + ' https://public.invalid/a socks5://[REDACTED]@proxy.invalid HTTP://[REDACTED]@other.invalid custom+scheme://[REDACTED]@host.invalid');
  });
});
