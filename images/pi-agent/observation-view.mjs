import { Buffer } from 'node:buffer';

/** 为当前 Pi 上下文生成可还原的终端增量；原始观察由控制端独立保存。 */
export class ObservationView {
  #previous = null;

  /** 清除旧上下文基线，确保下次观察提供完整画面。@return {void} */
  reset() {
    this.#previous = null;
  }

  /**
   * 投影一条已经确认的观察，不改写控制端原结果。
   * @param {object} result 完整工具回执。
   * @param {boolean} full 是否显式请求整屏。
   * @return {object} 带形态及必要基线的模型视图。
   */
  project(result, full = false) {
    if (!result || typeof result.observation_id !== 'string' || !result.observation_id
        || typeof result.screen !== 'string') return result;
    const previous = this.#previous;
    const complete = {...result, screen_mode: 'full'};
    this.#previous = {id: result.observation_id, screen: result.screen};
    if (!previous || full) return complete;
    const {screen, ...facts} = result;
    const base = {...facts, screen_base_observation_id: previous.id};
    if (screen === previous.screen) {
      return {...base, screen_mode: 'unchanged'};
    }
    const before = previous.screen.split('\n'), after = screen.split('\n');
    let prefix = 0, suffix = 0;
    while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix++;
    while (suffix < before.length - prefix && suffix < after.length - prefix
        && before[before.length - 1 - suffix] === after[after.length - 1 - suffix]) suffix++;
    const patch = {...base, screen_mode: 'patch', screen_patch: {
      start_line: prefix, delete_count: before.length - prefix - suffix,
      lines: after.slice(prefix, after.length - suffix),
    }};
    // 小画面或完全改变时，差异元数据可能更大；此时直接给 Pi 真实整屏。
    return Buffer.byteLength(JSON.stringify(patch)) < Buffer.byteLength(JSON.stringify(complete)) ? patch : complete;
  }
}
