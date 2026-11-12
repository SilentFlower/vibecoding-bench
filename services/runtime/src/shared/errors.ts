/** 可向调用方说明的本地合同错误，不暴露凭据或底层环境。 */
export class BridgeError extends Error {
  /** 创建带状态码的合同错误。
   * @param code 稳定错误代码。
   * @param message 中文说明。
   * @param status HTTP 状态。
   */
  constructor(public readonly code: string, message: string, public readonly status = 400) {
    super(message);
    this.name = 'BridgeError';
  }
}

/** 判断 JSON 边界是否为普通对象。
 * @param value 待检查值。
 * @return 仅对象且不是数组时为真。
 */
export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** 将未知错误转换成稳定文本。
 * @param error 异常值。
 * @return 供脱敏器进一步处理的文本。
 */
export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
