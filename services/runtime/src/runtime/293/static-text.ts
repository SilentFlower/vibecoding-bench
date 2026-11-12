/** 判断一个静态正文及其条件是否可保存在工厂的单项缓存中。
 * @param text 已经由原生纯格式化函数生成的正文。
 * @param dependencies 本次逐轮求值的原始条件；不接收会话对象。
 * @return 键和值合计不超过 64 KiB；六个工厂最多持有六项、384 KiB。
 */
export function staticTextFits(text: string, dependencies: readonly (string | boolean | number | null | undefined)[]): boolean {
  return Buffer.byteLength(text) + Buffer.byteLength(JSON.stringify(dependencies)) <= 64 * 1024;
}
