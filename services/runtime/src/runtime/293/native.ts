import type { JsonObject } from '../../shared/contracts';

/** 原生查询流水线中的消息或上下文记录。 */
export interface NativeRecord extends JsonObject {
  type: string;
  uuid?: string;
}

/** 固定 293 的内部业务消息实体。 */
export interface NativeMessage extends NativeRecord {
  uuid: string;
  message: { role: string; content: unknown; model?: string };
  promptId?: string;
  turnOrigin?: string;
  turnPosition?: { promptIndex: number; turnIndex: number };
}

/** 原生工具对象；桥接只读取声明，不调用执行方法。 */
export interface NativeTool extends JsonObject { name: string }

/** 当前原生权限投影，其余字段仍由官方工厂持有。 */
export interface NativePermission extends JsonObject { mode: string }

/** 原生代理定义集合，不在桥接里重写内置代理文本。 */
export interface NativeAgents extends JsonObject { activeAgents: JsonObject[]; allAgents: JsonObject[] }

/** 查询引擎交给底层模型构造器的实际参数。 */
export interface NativeModelCall extends JsonObject {
  messages: NativeRecord[];
  systemPrompt: string[];
  thinkingConfig: JsonObject;
  tools: NativeTool[];
  signal: AbortSignal;
  options: JsonObject;
}

/** 原生状态存储，生命周期限定在本轮会话根。 */
export interface NativeStore {
  /** 读取本轮状态快照。 @return 当前原生状态。 */
  getState(): JsonObject;
  /** 读取订阅快照。 @return 当前原生状态。 */
  getSnapshot(): JsonObject;
  /** 原子更新本轮状态。 @param update 状态变换。 @return 无返回值。 */
  setState(update: (value: JsonObject) => JsonObject): void;
  /** 订阅本轮变化。 @param callback 变化通知。 @return 取消订阅函数。 */
  subscribe(callback: () => void): () => void;
}

/** 来自已核对内嵌模块的消息工厂与查询入口。 */
export interface NativeCore {
  /** 创建用户消息。
   * @param value 官方工厂参数。
   * @return 官方消息实体。
   */
  Re(value: JsonObject): NativeMessage;
  /** 创建助手消息。
   * @param value 官方工厂参数。
   * @return 官方消息实体。
   */
  Kc(value: JsonObject): NativeMessage;
  /** 执行官方构造流程。
   * @param value 已核对的查询参数。
   * @return 官方异步事件序列。
   */
  K_t(value: NativeModelCall): AsyncGenerator<unknown>;
  /** 生成默认 CLI system。 @param tools 实际工具的名称投影。 @param model 模型。 @return 原生段落。 */
  VA(tools: { name: string }[], model: string): Promise<string[]>;
  /** 应用原生 system 选择规则。 @param value 工具上下文、默认及显式正文。 @return 原生段落。 */
  Kz(value: JsonObject): string[];
  /** 读取实际代理定义。 @param cwd 当前项目目录。 @return 原生代理集合。 */
  _R(cwd: string): Promise<NativeAgents>;
  /** 读取实际命令及技能。 @param cwd 当前项目目录。 @return 原生命令。 */
  _p(cwd: string): Promise<unknown[]>;
  /** 构造用户上下文。 @param session 本轮原生根。 @return 官方用户上下文。 */
  LT(session: NativeSession): Promise<JsonObject>;
  /** 构造系统上下文。 @param session 本轮原生根。 @return 官方系统上下文。 */
  Uz(session: NativeSession): Promise<JsonObject>;
  /** 计算下一轮位置；历史不足时不猜测。 @param messages 已有历史。 @param origin 实际来源。 @return 可证明的位置或空。 */
  Fyn(messages: NativeRecord[], origin: string): NativeMessage['turnPosition'];
  /** 生成 CLI 提醒。 @param text 原始输入或空。 @param context 原生工具上下文。 @param selection IDE 选择。 @param queued 本轮待投递项。 @param stamp 原生时间工厂。 @param messages 既有历史。 @param source 查询来源。 @param options 本轮提示词属性。 @return 原生记录序列。 */
  pie(text: string | null, context: JsonObject, selection: undefined, queued: unknown[], stamp: undefined, messages: NativeRecord[], source: string, options: JsonObject): AsyncGenerator<NativeRecord>;
  /** 规范化原生记录。 @param messages 输入记录。 @param tools 实际原生工具。 @param model 模型。 @param options 原生规范化选项。 @return 业务与提醒对应的消息实体。 */
  Ck(messages: NativeRecord[], tools?: NativeTool[], model?: string, options?: JsonObject): NativeMessage[];
  /** 官方自动压缩回调，仅作为原生依赖传递；单轮桥接禁用自动压缩。 */
  Cer: unknown;
}

/** 原生 SDK 及唯一默认发送入口。 */
export interface NativeApi {
  /** 创建官方 SDK。
   * @param value 上下文及发送选项。
   * @return 支持原始 Response 的官方客户端。
   */
  yN(value: JsonObject): Promise<{ beta: { messages: {
    /** 创建唯一原生消息请求。
     * @param body 官方构造的正文。
     * @param options 请求取消及头部选项。
     * @return 可取得原始响应的请求。
     */
    create(body: JsonObject, options: JsonObject): {
      /** 取得原始响应，交给桥接器独占读取。
       * @return 上游逻辑响应。
       */
      asResponse(): Promise<Response>;
    };
  } } }>;
  /** 经官方原生传输发送。
   * @param input 上游地址。
   * @param init 原始请求参数。
   * @return 上游原始逻辑响应。
   */
  Ree(input: RequestInfo | URL, init?: RequestInit): Promise<Response>;
}

/** 原生会话使用的项目目录。 */
export interface NativeProject { originalCwd: string; projectRoot: string; cwd: string }

/** 只声明本项目确实读取的原生会话字段。 */
export interface NativeSession {
  host: unknown;
  id: string;
  project: NativeProject | null;
  engineStore: {
    /** 绑定本轮状态。 @param store 本轮独立原生状态存储。 @return 无返回值。 */
    adopt(store: NativeStore): void;
  };
}

/** 固定 293 根会话工厂和作用域读取器。 */
export interface NativeState {
  /** 读取当前异步作用域的会话。
   * @return 当前原生根。
   */
  F(): NativeSession;
  /** 创建独立账本、请求日志和临时状态的根会话。
   * @param value 已有账号 host、本轮 ID 与项目目录。
   * @return 全新原生根。
   */
  nEr(value: { host: unknown; id: string; project: NativeProject | null }): NativeSession;
  /** 注册异步上下文读取器。
   * @param getter 返回当前会话的读取器。
   * @return 无返回值。
   */
  yLs(getter: () => { session: NativeSession } | undefined): void;
  /** 设置本轮会话关联。
   * @param id 本轮会话 ID。
   * @param transition 已验证的迁移类型。
   * @return 无返回值。
   */
  t_(id: string, transition: string): void;
  /** 选择真实 CLI 的交互装配分支。 @param value 是否交互式 CLI。 @return 无返回值。 */
  vwo(value: boolean): void;
  /** 设置 CLI 的问题预览格式。 @param value 官方格式。 @return 无返回值。 */
  REr(value: 'markdown'): void;
  /** 绑定本轮模型选择。 @param model 模型名称。 @return 无返回值。 */
  bf(model: string): void;
}

/** 原版预加载与精简静态入口共享的原生绑定。 */
export interface NativeBindings {
  core: NativeCore;
  api: NativeApi;
  state: NativeState;
  context: {
    /** 完成官方配置初始化。
     * @return 初始化收口。
     */
    Nst(): Promise<void>;
    /** 计算 CLI 默认 thinking。 @param enabled 配置中的开关。 @param config 会话 thinking。 @param model 模型。 @return 原生 thinking 配置。 */
    kps(enabled: boolean | undefined, config: JsonObject, model: string): JsonObject;
    /** 读取配置中的 thinking 开关。 @return 配置值或缺省。 */
    n4(): boolean | undefined;
    /** 更新专用 CLI 配置。 @param update 配置变换。 @return 配置写入已收口。 */
    Ae(update: (value: JsonObject) => JsonObject): Promise<void>;
    /** 读取密钥的本地使用决定。 @param marker 原生密钥标识。 @return 本地确认状态。 */
    Iyr(marker: string): 'approved' | 'rejected' | 'new';
    /** 生成官方本地密钥标识。 @param key 显式配置的密钥。 @return 官方标识。 */
    Lle(key: string): string;
    /** 读取有效的本地使用列表。 @param value 专用配置。 @return 已确认和已拒绝列表。 */
    VH(value: JsonObject): { approved: string[]; rejected: string[] };
    /** 初始化官方第一方 logger。 @return 初始化完成，无需额外存储适配。 */
    SLe(): void;
    /** 检查官方第一方事件资格。 @return 原生策略是否允许。 */
    a4(): boolean;
    /** 收口第一方发送任务。 @return 原生收口完成。 */
    MDs(): Promise<void>;
    /** 关闭官方第一方 logger。 @return 原生关闭完成。 */
    bLe(): Promise<void>;
    /** 使用官方采集器记录并生成原生 metadata。 @param name 原生事件名。 @param metadata 原生事件参数。 @return 采集完成，不代表已上传。 */
    Jk(name: string, metadata?: JsonObject): Promise<void>;
    /** 应用官方事件采样。 @param name 原生事件名。 @return 零表示丢弃，null 表示无额外采样。 */
    gyr(name: string): number | null;
    /** 按官方目录规则脱敏 metadata。 @param metadata 原生事件参数。 @return 原生脱敏后的事件参数。 */
    Yus(metadata: JsonObject): JsonObject;
    /** 检查原生模型脱敏目录是否可用。 @return 是否已就绪或允许使用当前回退。 */
    Nco(): boolean;
    /** 等待官方模型脱敏目录。 @return 官方目录初始化收口。 */
    w9t(): Promise<unknown>;
    /** 登记并转换模型的遥测名称。 @param model 原生模型名。 @return 原生安全名称。 */
    gDn(model: string): string;
    /** 读取当前原生模型选择。 @return 当前模型名。 */
    tt(): string;
  };
  analytics: {
    /** 绑定当前 host 的事件接收器，仅首次绑定生效。
     * @param sink 接收原生代码已经产生的事件，不自行生成事件。
     * @return 接收器绑定完成。
     */
    G_o(sink: {
      /** 后台记录事件。 @param name 事件名。 @param metadata 原生参数。 @return 无返回值。 */
      logEvent(name: string, metadata?: JsonObject): void;
      /** 记录可等待事件。 @param name 事件名。 @param metadata 原生参数。 @return 原生采集完成。 */
      logEventAsync(name: string, metadata?: JsonObject): Promise<void>;
    }): void;
  };
  network: {
    /** 为官方 HTTP 客户端配置代理、CA 和连接代理。
     * @return 本机网络配置完成，不产生模型请求。
     */
    Jb(): void;
  };
  permissions: {
    /** 创建官方空权限上下文。
     * @return 原生权限对象。
     */
    su(): unknown;
  };
  cliTools: {
    /** 原生目录；getAllBaseTools 返回实际内置工具，其他方法由原生上下文直接消费。 */
    Bq: JsonObject & { getAllBaseTools: () => NativeTool[] };
    /** 按权限取得原生工具。 @param permission 当前权限。 @param options 代理筛选。 @return 工具池。 */
    OD(permission: NativePermission, options?: JsonObject): NativeTool[];
  };
  cliToolPool: {
    /** 合并并排序工具池。 @param initial 初始工具。 @param tools 当前工具。 @param mode 权限模式。 @param declared 已声明工具。 @return 工具池。 */
    $0t(initial: NativeTool[], tools: NativeTool[], mode: string, declared: NativeTool[]): NativeTool[];
    /** 应用最终权限筛选。 @param tools 工具池。 @param permission 当前权限。 @return 可用工具。 */
    F0t(tools: NativeTool[], permission: NativePermission): NativeTool[];
  };
  cliPermissions: {
    /** 解析 CLI 初始权限。 @param value 显式启动选项。 @return 官方选择。 */
    XUr(value: JsonObject): { mode: string };
    /** 构造权限上下文。 @param value 实际工具及启动选项。 @return 原生权限。 */
    JUr(value: JsonObject): Promise<{ toolPermissionContext: NativePermission }>;
    /** 核对模型权限能力。 @param permission 初始权限。 @param fast 是否快速模式。 @return 原生状态变换。 */
    B1e(permission: NativePermission, fast: boolean): Promise<{ updateContext: (permission: NativePermission) => NativePermission }>;
    /** 收口本地已知的初始选择。 @param permission 初始权限。 @return 有效权限。 */
    dmn(permission: NativePermission): NativePermission;
  };
  cliState: {
    /** 创建原生默认状态。 @return 全新状态。 */
    yF(): JsonObject;
  };
  cliStore: {
    /** 创建本轮状态容器。 @param initial 初始状态。 @return 原生容器。 */
    rs(initial: JsonObject): NativeStore;
  };
  cliLenses: {
    /** 创建原生状态访问器。 @param get 读取状态。 @param set 更新状态。 @return 原生访问器。 */
    f9e(get: NativeStore['getState'], set: NativeStore['setState']): JsonObject;
  };
  cliTasks: {
    /** 创建本轮任务视图。 @param get 读取状态。 @param set 更新状态。 @return 原生视图。 */
    rg(get: NativeStore['getState'], set: NativeStore['setState']): unknown;
  };
  cliToolState: {
    /** 本轮独立的原生工具状态构造器。 */
    jM: new () => unknown;
  };
  cliFiles: {
    dC: number;
    /** 创建原生读取状态。 @param limit 原生容量。 @return 本轮读取状态。 */
    Uk(limit: number): unknown;
  };
  cliQuery: {
    /** 执行 CLI 查询装配；桥接只允许首次受控模型发送，响应读取收口后取消原生解析。 @param value 原生本轮上下文及受控模型构造器。 @return 原生事件。 */
    OM(value: JsonObject): AsyncGenerator<unknown>;
  };
  cliReplacements: {
    /** 建立本轮内容追踪。 @param messages 本轮历史。 @return 原生追踪状态或缺省。 */
    p7o(messages: NativeRecord[]): unknown;
  };
  cliSkills: {
    /** 注册官方内置扩展定义。 @return 无返回值。 */
    Hoe(): void;
    /** 注册官方内置技能。 @return 无返回值。 */
    $8e(): void;
  };
  cliSource: {
    /** 生成 CLI 主线程来源。 @return 受输出风格影响的原生来源。 */
    u1e(): string;
  };
}
