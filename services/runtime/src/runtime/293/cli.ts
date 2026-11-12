import type { JsonObject, PreparedInput } from '../../shared/contracts';
import { BridgeError, isObject } from '../../shared/errors';
import type { NativeBindings, NativeMessage, NativeModelCall, NativeRecord, NativeTool } from './native';

/** 本轮 CLI 原生装配结果，不在请求间共享可变状态。 */
export interface CliPreparation {
  agent: JsonObject;
  business: NativeMessage[];
  messages: NativeRecord[];
  systemPrompt: string[];
  userContext: JsonObject;
  systemContext: JsonObject;
  toolContext: JsonObject;
  nativeTools: NativeTool[];
  querySource: string;
}

/** 初始化固定账号的 CLI 分支和官方内置定义。
 * @param bindings 已核验的固定版本绑定。
 * @return 本地初始化完成，不运行模型或工具。
 */
export async function initializeCli(bindings: NativeBindings): Promise<void> {
  bindings.state.vwo(true);
  bindings.state.REr('markdown');
  await bindings.context.Nst();
  const key = process.env.ANTHROPIC_API_KEY;
  if (key) {
    const marker = bindings.context.Lle(key);
    const decision = bindings.context.Iyr(marker);
    if (decision === 'rejected') throw new BridgeError('native_configuration', '专用 CLI 配置已拒绝当前显式密钥', 503);
    if (decision === 'new') {
      // 控制配置中的显式密钥已授权给此引擎使用；只记录 CLI 同样的本地确认，不登录或保存完整密钥。
      await bindings.context.Ae(value => {
        const { approved, rejected } = bindings.context.VH(value);
        return { ...value, customApiKeyResponses: { approved: [...approved, marker], rejected } };
      });
      if (bindings.context.Iyr(marker) !== 'approved') throw new BridgeError('native_configuration', '无法在专用 CLI 配置中保存显式密钥的本地使用确认', 503);
    }
  }
  bindings.cliSkills.Hoe();
  bindings.cliSkills.$8e();
}

/** 为单轮调用建立真正的 CLI 提示词、工具和消息上下文。
 * @param prepared 已验证的输入及关联。
 * @param bindings 固定原生绑定。
 * @param system 显式业务正文；缺省时使用原生默认正文。
 * @param thinking 已验证的显式 thinking；缺省时走 CLI 默认计算。
 * @param abort 本轮构造专用取消控制器。
 * @return 全新原生根内的 CLI 装配参数。
 */
export async function prepareCli(prepared: PreparedInput, bindings: NativeBindings, system: string[] | undefined, thinking: JsonObject | undefined, abort: AbortController): Promise<CliPreparation> {
  const { body } = prepared.input;
  const requestedTools = body.tools ?? [];
  const context = prepared.context;
  let promptIndex = -1;
  // 官方轮次选择器跳过任何含工具结果的消息，ID 必须归到此前真实用户轮次。
  for (let index = body.messages.length - 1; index >= 0; index--) {
    const message = body.messages[index]!;
    if (message.role === 'user' && (typeof message.content === 'string' || !message.content.some(block => block.type === 'tool_result'))) { promptIndex = index; break; }
  }
  if (promptIndex < 0) throw new BridgeError('unsupported_parameter', '普通 API 历史缺少可归属 Prompt ID 的用户轮次，需要提供完整用户与工具历史', 422);
  const { core } = bindings;
  bindings.state.bf(body.model);
  const querySource = context.querySource;
  if (context.requestClass === 'main' && bindings.cliSource.u1e() !== querySource) throw new BridgeError('unsupported_parameter', '当前输出风格的原生来源与已解析上下文不一致', 422);
  const agent: JsonObject = context.agentKind === 'main' ? { agentType: 'main', agentId: context.agentId ?? context.sessionId } : {
    agentType: context.agentKind, agentId: context.agentId, parentAgentId: context.parentAgentId,
    parentPromptId: context.promptId, isMainSession: false, workflowRunId: context.workflowRunId,
  };
  const selected = bindings.cliPermissions.XUr({});
  // 三条本地配置读取不相互依赖；并行执行，结果仍全部归属于本轮新根。
  const [permission, agents, commands] = await Promise.all([
    (async () => {
      const { toolPermissionContext: initialPermission } = await bindings.cliPermissions.JUr({
        allowedToolsCli: [], disallowedToolsCli: [], addDirs: [], permissionMode: selected.mode,
        getAllBaseTools: bindings.cliTools.Bq.getAllBaseTools,
        baseToolsCli: [''],
      });
      const settledPermission = bindings.cliPermissions.dmn(initialPermission);
      const { updateContext } = await bindings.cliPermissions.B1e(settledPermission, false);
      return updateContext(settledPermission);
    })(),
    core._R(process.cwd()), core._p(process.cwd()),
  ]);
  // API 只声明调用方提供的工具，禁用内置池，避免模型选择调用方没有实现的 CC 工具。
  const nativeTools: NativeTool[] = [];
  const promptTools = requestedTools.map(tool => {
    if (typeof tool.name !== 'string' || !tool.name) throw new BridgeError('unsupported_parameter', '显式工具必须有非空名称', 422);
    return { name: tool.name };
  });
  const state = bindings.cliStore.rs({ ...bindings.cliState.yF(), mainLoopModel: body.model, toolPermissionContext: permission, agentDefinitions: agents });
  const session = bindings.state.F();
  session.engineStore.adopt(state);
  const business: NativeMessage[] = [];
  for (const [index, message] of body.messages.entries()) {
    const content = typeof message.content === 'string' ? [{ type: 'text', text: message.content }] : structuredClone(message.content);
    if (message.role === 'assistant') {
      const value = core.Kc({ content });
      value.message.model = body.model;
      business.push(value);
      continue;
    }
    const human = context.requestClass === 'main' && context.agentKind === 'main' && content.length > 0 && !content.some(block => block.type === 'tool_result');
    const value = core.Re({ content, ...(index === promptIndex ? { promptId: context.promptId } : {}), ...(human ? { origin: { kind: 'human' } } : {}) });
    if (human) {
      value.turnOrigin = 'human';
      value.turnPosition = core.Fyn(business, 'human');
    }
    business.push(value);
  }
  const toolContext: JsonObject = {
    session, agentContext: agent,
    ...(context.agentKind !== 'main' ? { agentId: context.agentId, agentType: context.agentType } : {}),
    options: {
      commands, tools: nativeTools, toolCatalog: bindings.cliTools.Bq, mainLoopModel: body.model,
      thinkingConfig: thinking ?? bindings.context.kps(bindings.context.n4(), { type: 'disabled' }, body.model),
      mcpClients: [], mcpResources: {}, isNonInteractiveSession: false, agentDefinitions: agents,
      ...(system !== undefined ? { customSystemPrompt: system } : {}),
      runQuery: () => { throw new BridgeError('unsupported_parameter', '单轮桥接不启动本地代理循环', 422); },
    },
    abortController: abort, readFileState: bindings.cliFiles.Uk(bindings.cliFiles.dC), toolState: new bindings.cliToolState.jM(),
    // 业务排队由控制层负责；原生装配看到的是没有终端通知的只读空队列。
    messageQueue: {
      countRemainingWakePollEventsAfter: () => 0, isMidTurnFoldSuspended: () => false,
      getCommandsByMaxPriority: () => [], getCommandQueue: () => [], getCommandQueueSnapshot: () => [], subscribe: () => () => {},
    },
    getAppState: state.getState, setAppState: state.setState,
    ...bindings.cliLenses.f9e(state.getState, state.setState), taskRegistry: bindings.cliTasks.rg(state.getState, state.setState),
    contentReplacementState: bindings.cliReplacements.p7o(business), messages: business,
    nestedMemoryAttachmentTriggers: [], dynamicSkillDirTriggers: [],
    getFileHistoryState: () => undefined,
    applyFileHistoryOp: () => { throw new Error('构造阶段禁止修改文件历史'); },
    applyAttributionOp: () => { throw new Error('构造阶段禁止修改提交归因'); },
  };
  const latest = business.at(-1);
  const ordinary = latest?.type === 'user' && latest.turnOrigin === 'human';
  const [records, [defaultSystemPrompt, userContext, systemContext]] = await Promise.all([
    (async () => {
      const records: NativeRecord[] = [];
      for await (const record of core.pie(null, toolContext, undefined, [], undefined, business.slice(0, -1), querySource, { isRegularUserPrompt: ordinary, isHumanTypedPrompt: ordinary })) records.push(record);
      return records;
    })(),
    Promise.all([core.VA(promptTools, body.model), core.LT(session), core.Uz(session)]),
  ]);
  const messages = [...business.slice(0, -1), ...records, ...(latest ? [latest] : [])];
  const definition = context.agentKind !== 'main' && system === undefined ? agents.activeAgents.find(value => value.agentType === context.agentType) : undefined;
  if (context.agentKind !== 'main' && context.agentType && system === undefined && !definition) throw new BridgeError('unsupported_parameter', '当前子代理没有可用的原生定义，需要显式业务 system', 422);
  const systemPrompt = core.Kz({ toolUseContext: toolContext, defaultSystemPrompt, customSystemPrompt: system, ...(definition ? { mainThreadAgentDefinition: definition } : {}) });
  if (abort.signal.aborted) throw new DOMException('请求已取消', 'AbortError');
  return { agent, business, messages, systemPrompt, userContext, systemContext, toolContext, nativeTools, querySource };
}

/** 校验查询引擎交回的最小模型构造参数。
 * @param value 原生调用参数。
 * @return 已知参数可供固定 K_t 使用。
 */
export function isNativeModelCall(value: unknown): value is NativeModelCall {
  return isObject(value) && Array.isArray(value.messages) && Array.isArray(value.systemPrompt) && Array.isArray(value.tools) && isObject(value.options) && isObject(value.thinkingConfig) && value.signal instanceof AbortSignal;
}
