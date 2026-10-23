/**
 * 为单个账号运行持久 Pi 会话，通过独立管道调用控制端工具。
 * 配置与密钥仅从 stdin 接收，stdout 只发布协议事件。
 */
import { mkdir } from 'node:fs/promises';
import { AuthStorage, createAgentSession, DefaultResourceLoader, defineTool, ModelRegistry,
  SessionManager, SettingsManager } from '@earendil-works/pi-coding-agent';

const pending = new Map();
let session;
let configured = false;
let input = '';
let sequence = 0;

/**
 * 写入一条有界协议事件。
 * @param {object} value 事件内容。
 * @return {void}
 */
function emit(value) {
  process.stdout.write(JSON.stringify(value) + '\n');
}

/**
 * 将工具调用交给 Python 所有者执行，模型无法自行选择账号或连接端点。
 * @param {string} name 工具名。
 * @param {string} toolCallId Pi 原始工具调用标识。
 * @param {object} args 已校验参数。
 * @param {AbortSignal|undefined} signal 取消信号。
 * @return {Promise<object>} 工具结果。
 */
function callTool(name, toolCallId, args, signal) {
  const id = `${++sequence}`;
  return new Promise((resolve, reject) => {
    const abort = () => {
      pending.delete(id);
      reject(new Error('操作已中止'));
    };
    if (signal?.aborted) return abort();
    signal?.addEventListener('abort', abort, {once: true});
    pending.set(id, {
      resolve: result => {
        signal?.removeEventListener('abort', abort);
        resolve({content: [{type: 'text', text: JSON.stringify(result)}], details: {}});
      },
      reject,
    });
    emit({type: 'tool', id, name, tool_call_id: toolCallId, args});
  });
}

/**
 * 按明确的 SDK 能力创建隔离会话，不自动发现宿主或项目扩展。
 * @param {object} config 私有启动配置。
 * @return {Promise<void>} 当前 Pi 指挥轮次结束。
 */
async function run(config) {
  await mkdir(config.session_dir, {recursive: true, mode: 0o700});
  const authStorage = AuthStorage.inMemory();
  const modelRegistry = ModelRegistry.inMemory(authStorage);
  authStorage.setRuntimeApiKey('projects', config.api_key);
  modelRegistry.registerProvider('projects', {
    baseUrl: config.base_url,
    apiKey: 'runtime-only',
    api: 'openai-completions',
    models: config.models.map(id => ({id, name: id, reasoning: false, input: ['text'],
      contextWindow: 32768, maxTokens: 4096,
      cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0},
      compat: {supportsDeveloperRole: false, supportsStore: false, supportsReasoningEffort: false,
        maxTokensField: 'max_tokens'},
    })),
  });
  const customTools = (config.tools || []).map(tool => defineTool({
    name: tool.name, label: tool.name, description: tool.description,
    parameters: tool.parameters, executionMode: 'sequential',
    execute: (toolCallId, args, signal) => callTool(tool.name, toolCallId, args, signal),
  }));
  const settingsManager = SettingsManager.inMemory({
    retry: {enabled: false, provider: {timeoutMs: 60000, maxRetries: 0}},
    compaction: {enabled: true, reserveTokens: 8192, keepRecentTokens: 12000},
  });
  const resourceLoader = new DefaultResourceLoader({
    cwd: config.session_dir, agentDir: config.session_dir, settingsManager,
    noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
    systemPrompt: config.instructions,
  });
  await resourceLoader.reload();
  const sessionManager = config.session_file
    ? SessionManager.open(config.session_file, config.session_dir)
    : SessionManager.create(config.session_dir, config.session_dir);
  ({session} = await createAgentSession({cwd: config.session_dir, agentDir: config.session_dir,
    authStorage, modelRegistry, settingsManager, resourceLoader, sessionManager,
    model: modelRegistry.find('projects', config.models[0]), thinkingLevel: 'off',
    tools: customTools.map(tool => tool.name), customTools,
  }));
  session.subscribe(event => {
    if (event.type === 'message_end' && event.message.role === 'assistant') {
      const message = event.message;
      const measured = message.usage && ['input', 'output', 'cacheRead', 'cacheWrite']
        .some(field => message.usage[field] > 0);
      emit({type: 'assistant', model: message.model, stop_reason: message.stopReason,
        message_id: `${session.sessionId}:${message.timestamp}`, usage: measured ? message.usage : null,
        text: message.content.filter(part => part.type === 'text').map(part => part.text).join('\n')});
    }
  });
  emit({type: 'ready', session_file: session.sessionFile, session_id: session.sessionId});
  try {
    let message;
    for (let index = 0; index < config.models.length; index += 1) {
      if (index) await session.setModel(modelRegistry.find('projects', config.models[index]));
      await session.prompt(config.prompt, {expandPromptTemplates: false});
      message = session.messages.findLast(value => value.role === 'assistant');
      // 只有尚未执行工具的明确额度或临时服务错误允许换模型，避免重放已经产生的终端操作。
      const retryable = /\b(402|429|500|502|503|504)\b/.test(message?.errorMessage || '');
      if (message?.stopReason !== 'error' || sequence || !retryable) break;
    }
    if (message?.stopReason === 'error') {
      emit({type: 'error', message: 'Pi 模型请求失败，请检查模型的流式响应及工具调用兼容性'});
    } else {
      emit({type: 'settled'});
    }
  } finally {
    session.dispose();
  }
}

/**
 * 处理完整 JSONL 记录；取消命令可在模型或工具等待期间立即进入。
 * @param {object} record 输入记录。
 * @return {void}
 */
function receive(record) {
  if (record.type === 'configure' && !configured) {
    configured = true;
    run(record).catch(() => emit({type: 'error', message: 'Pi 运行时初始化或执行失败'}))
      .finally(() => process.exit());
  } else if (record.type === 'tool_result') {
    const request = pending.get(record.id);
    pending.delete(record.id);
    request?.resolve(record.result);
  } else if (record.type === 'abort') {
    session?.abort();
    for (const request of pending.values()) request.reject(new Error('指挥已停止'));
    pending.clear();
  }
}

process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  input += chunk;
  if (Buffer.byteLength(input) > 2 * 1024 * 1024) process.exit(2);
  let boundary;
  while ((boundary = input.indexOf('\n')) >= 0) {
    const line = input.slice(0, boundary);
    input = input.slice(boundary + 1);
    if (!line.trim()) continue;
    try { receive(JSON.parse(line)); } catch { emit({type: 'error', message: 'Pi 管道协议无效'}); }
  }
});
process.stdin.on('end', () => {
  session?.abort().finally(() => process.exit());
  if (!session) process.exit();
});
