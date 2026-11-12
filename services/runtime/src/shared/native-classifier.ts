import { createHash } from 'node:crypto';
import type { MessageBody, NativeClassification } from './contracts';

// 摘要来自已固定 SHA 的官方 2.1.293 及实际 CLI 实收，不保存完整专有提示词。
const SYSTEM_SHA = '6b368647be9358ea39f4a3a36cb73a5f7b50129eba0b9d5c1c95e44bb9a40ec7';
const FOOTER_S1_SHA = '6ac77994fdcda7ccf62f81cf4e8b1d8c8064e1958afe5627265a9ec17a07f720';
const FOOTER_S2_SHA = 'a82c52d8072c24f95f54f8e47d2b6a78914e8d31de7f0e4213d5944150f3ae68';
const DENY_SUFFIX_SHA = '98e88fbc391d18ae0af0dfcf5ad737ae60d4133610c7967c0f2d62e702d338a3';
const DENY_PREFIX = '- User Deny Rules: The user has configured these permission deny rules: ';
const CLI_IDENTITY_SHA = '2719b7a469d904b3281d8488976f33103944211279bddf04c05bca44d184dae6';
const TITLE_SYSTEM_SHA = '765b5ba2fa0a315a3c749c7e54bf5cef450084a745eb01e66371b8b6359d4752';
const TITLE_FOOTER_SHA = '30704b4d05983bebf62600d91882d0f6c98a0748dc7ae578cece46864bb0f515';
const TITLE_LANGUAGE_FOOTER_SHA = '034169c4eb412ab28e3cc53bb088798ab5eb7b24862a4c5c1e38d7abe37dedc0';
const COMPACT_PROMPT_SHA = '63e2bfb4ded280d5057a66d8a034ef352a73960d97d955b990e78f04f0db1fb0';
const COMPACT_FOOTER_SHA = 'e8304a513b9da6144d75836dfc5b7bf260a6cfd853ad6b02c19174cabe6e19cf';
const COMPACT_INSTRUCTIONS = '\n\nAdditional Instructions:\n';

function digest(text: string): string { return createHash('sha256').update(text).digest('hex'); }

/** 识别已经过原生入站校验的固定分类构造，未知变体保持未识别。
 * @param body 保留原始业务字段的固定 293 原生正文。
 * @return 已验证的用途证据，或未知时的 undefined。
 */
export function readNativeClassification(body: MessageBody): NativeClassification | undefined {
  return readPermissionClassifier(body) ?? readSessionTitle(body) ?? readCompaction(body);
}

/** 核对原生权限分类的两阶段静态构造。
 * @param body 已验证原生正文。
 * @return 对应阶段证据，或未识别。
 */
function readPermissionClassifier(body: MessageBody): NativeClassification | undefined {
  if (body.temperature !== 1 || body.stream === true || body.tools !== undefined || body.tool_choice !== undefined || body.output_config !== undefined) return;
  const firstStage = Array.isArray(body.stop_sequences) && body.stop_sequences.length === 1 && body.stop_sequences[0] === '</block>';
  if (!firstStage && body.stop_sequences !== undefined) return;
  if (!Array.isArray(body.system) || body.system.length !== 2 || body.system[1]!.type !== 'text' || typeof body.system[1]!.text !== 'string') return;
  const text = body.system[1]!.text;
  if (text.length > 160000) return;
  let valid = true, replacements = 0;
  // 只开放官方声明的规则列表插槽；其余整段静态内容仍须逐字节符合固定摘要。
  const normalized = text.replace(/^- User Deny Rules:[^\r\n]*/gm, line => {
    const boundary = line.indexOf('. Each rule names');
    const rules = line.slice(DENY_PREFIX.length, boundary);
    if (++replacements > 1 || !line.startsWith(DENY_PREFIX) || line.length > 16384 || !/^`[^`\r\n]+`(?:, `[^`\r\n]+`)*$/.test(rules) || digest(line.slice(boundary)) !== DENY_SUFFIX_SHA) { valid = false; return line; }
    return '';
  });
  if (!valid || digest(normalized) !== SYSTEM_SHA) return;
  if (body.messages.length < 1 || body.messages.length > 2 || body.messages.some(m => m.role !== 'user' || !Array.isArray(m.content) || !m.content.every(b => b.type === 'text' && typeof b.text === 'string'))) return;
  const blocks = body.messages.at(-1)!.content;
  if (!Array.isArray(blocks) || blocks.length < 4 || blocks[0]!.text !== '<transcript>\n' || blocks.at(-2)!.text !== '</transcript>\n') return;
  const footer = blocks.at(-1)!.text;
  if (typeof footer !== 'string' || digest(footer) !== (firstStage ? FOOTER_S1_SHA : FOOTER_S2_SHA)) return;
  // 官方各阶段的输出上限还会叠加思考预算，预算值本身不是分类身份。
  return { purpose: 'auto_permission_classifier', source: 'native_profile', profile: firstStage ? 'cc293-auto-mode-xml-s1' : 'cc293-auto-mode-xml-s2' };
}

/** 核对标题生成的完整静态 system 和单条会话包装，不以短提示词猜用途。
 * @param body 已验证原生正文。
 * @return 标题生成证据，或未识别。
 */
function readSessionTitle(body: MessageBody): NativeClassification | undefined {
  if (body.tools?.length || body.tool_choice !== undefined || !Array.isArray(body.system) || body.system.length !== 3) return;
  const identity = body.system[1]!, system = body.system[2]!;
  if (identity.type !== 'text' || typeof identity.text !== 'string' || identity.text.length > 512 || digest(identity.text) !== CLI_IDENTITY_SHA || system.type !== 'text' || typeof system.text !== 'string' || system.text.length > 160000 || digest(system.text) !== TITLE_SYSTEM_SHA) return;
  if (body.messages.length !== 1 || body.messages[0]!.role !== 'user') return;
  const blocks = body.messages[0]!.content;
  if (!Array.isArray(blocks) || blocks.length !== 1 || blocks[0]!.type !== 'text' || typeof blocks[0]!.text !== 'string') return;
  const text = blocks[0]!.text, boundary = '\n</session>\n\n', footer = text.lastIndexOf(boundary);
  if (!text.startsWith('<session>\n') || footer < '<session>\n'.length) return;
  const suffix = text.slice(footer + boundary.length);
  if (digest(suffix) !== TITLE_FOOTER_SHA) {
    // 固定 293 的标题构造只在此插入 language 设置；完整静态收尾仍须匹配。
    const prefix = 'Write the title in ', end = suffix.lastIndexOf('. Keep technical terms');
    if (!suffix.startsWith(prefix) || end <= prefix.length || end - prefix.length > 512 || digest(prefix + '<language>' + suffix.slice(end)) !== TITLE_LANGUAGE_FOOTER_SHA) return;
  }
  return { purpose: 'session_title', source: 'native_profile', profile: 'cc293-session-title-v1' };
}

/** 核对末尾真实压缩指令，保留此前消息和可变的附加压缩要求。
 * @param body 已验证原生正文。
 * @return 手动或自动压缩共用的构造证据，或未识别。
 */
function readCompaction(body: MessageBody): NativeClassification | undefined {
  const message = body.messages.at(-1);
  if (message?.role !== 'user') return;
  const block = Array.isArray(message.content) ? message.content.at(-1) : undefined;
  // 无工具入口会直接使用字符串；带工具的原生历史则把压缩指令放在末尾文本块。
  const text = typeof message.content === 'string' ? message.content : block?.type === 'text' ? block.text : undefined;
  if (typeof text !== 'string' || text.length > 160000) return;
  const footer = text.lastIndexOf('\n\nREMINDER:');
  if (footer < 0 || digest(text.slice(footer)) !== COMPACT_FOOTER_SHA) return;
  const instructions = text.indexOf(COMPACT_INSTRUCTIONS);
  // 官方只在完整静态提示词与固定收尾之间追加用户要求；不能删除其他任意段落后凑摘要。
  if (instructions >= 0 && (instructions >= footer || !text.slice(instructions + COMPACT_INSTRUCTIONS.length, footer).trim())) return;
  const normalized = instructions < 0 ? text : text.slice(0, instructions) + text.slice(footer);
  if (digest(normalized) !== COMPACT_PROMPT_SHA) return;
  return { purpose: 'compaction', source: 'native_profile', profile: 'cc293-compact-full-v1' };
}
