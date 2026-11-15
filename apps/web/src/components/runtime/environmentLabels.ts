/** 既有运行时状态的中文含义。 */
export const criuStates:Record<string,string> = {disabled: '已关闭', not_installed: '镜像待升级', requires_rebuild: '待应用',
  preparing: '模板准备中', ready: '模板已就绪', unavailable: '当前使用普通启动', unknown: '状态待核对'};

/** 既有运行时状态的中文含义。 */
export const criuReasons:Record<string,string> = {legacy_backend: '当前为普通发送后端', platform_disabled: '平台已关闭加速',
  account_disabled: '账号已手动关闭', image_unsupported: '当前账号镜像尚未安装恢复器',
  memory_budget: '当前发送器内存额度不足以恢复，继续普通启动', container_rebuild_required: '空闲应用设置后启用恢复入口',
  controller_preflight_failed: '恢复环境预检失败，继续普通启动', controller_unavailable: '恢复器暂不可用',
  kernel_unsupported: '当前内核尚未支持恢复，请选择配套新版', template_failed: '模板准备失败，正在退避',
  template_preparing: '后台正在准备零模型模板', telemetry_missing: '当前版本尚未提供恢复状态',
  telemetry_stale: '状态已过期，等待同代巡检', binding_unverified: '环境绑定待核对',
  identity_changed: '账号身份已变化，等待重新准备', environment_stopped: '环境已停止', read_failed: '恢复状态读取失败'};

/** 既有运行时状态的中文含义。 */
export const preparationReasons:Record<string,string> = {identity_changed: '运行身份已变化', worker_unavailable: '进程退出或管道异常',
    check_expired: '最近检查已过期', check_failed: '状态检查失败', preparation_failed: '本地准备失败',
    invalidated: '准备已失效', capability_unknown: '原生能力待核对', binding_unverified: '最近快照属于其他环境或内核代次，等待当前代次检查',
    read_failed: '准备状态读取失败', snapshot_missing: '尚未收到本账号的准备快照',
    snapshot_pending: '等待首次检查返回当前环境快照',
    backend_pending: '已选择原生运行时，等待环境准备',
    native_sender_budget_missing: '原生发送器内存预算尚未配置，请配置后重试',
    native_sender_budget_insufficient: '原生发送器内存预算不足以覆盖当前并发，请调整后重试',
    account_memory_insufficient: '账号总内存不足以容纳网络、原生发送器和 CLI，请调整后重试',
    maintenance: '账号正在维护', system_maintenance: '平台更新中，结束后自动准备', sleeping: '环境休眠', disabled: '账号已停用'};

/** 既有运行时状态的中文含义。 */
export const tlsStates:Record<string,string> = {not_installed: '需系统更新安装采集器', disabled: '已关闭', stopped: '停止待启动', preparing: '准备中', ready: '已就绪', unavailable: '暂不可用'};

/** 既有运行时状态的中文含义。 */
export const tlsReasons:Record<string,string> = {OBSERVER_NOT_CONFIGURED: '采集器尚未安装', OBSERVER_STATUS_STALE: '检查结果已过期',
    OBSERVER_STATUS_UNAVAILABLE: '等待实际检查', IMAGE_NOT_ADMITTED: '当前内核尚未准入',
    PROBE_ATTACH_FAILED: '探针附着失败', BPF_LOAD_FAILED: '探针加载失败',
    OBSERVER_FAILED: '采集器已退出', CAPTURE_PREPARING: '后台准备中'};
