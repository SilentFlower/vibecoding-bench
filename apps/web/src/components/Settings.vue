<script setup lang="ts">
import { ref, onMounted, computed, nextTick } from 'vue';
import { api, type PrimeLogEntry } from '../api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableEmpty,
} from '@/components/ui/table';
import { NumberInput, ChoiceSelect, SearchInput } from './ui/controls';
import { Activity, Box, ShieldCheck, Globe, Clock, Settings2, FileText } from './ui/icon';
import { settingsGroups, type SettingField } from '../lib/settingsSchema';
import '../settings-design.css';
import { useToast } from '../composables/useToast';

const { show: toast } = useToast();

/** 权重表单 */
const w7d = ref('0.5');
const w5h = ref('0.3');
const wconc = ref('0.2');
/** v3 配置只影响新会话排序，稳定绑定和平滑发送持续生效。 */
const v3Mode = ref('smart');
const v3WaitSeconds = ref<string | number>('120');
const v3Weights = ref<Array<string | number>>(['1', '0.8', '1', '0.5']);
const isValidV3 = computed(() => {
  const wait = String(v3WaitSeconds.value).trim();
  const weights = v3Weights.value.map(value => Number(String(value).trim()));
  return ['smart', 'legacy_score'].includes(v3Mode.value)
    && /^\d+$/.test(wait) && Number(wait) >= 1 && Number(wait) <= 120
    && v3Weights.value.every(value => String(value).trim() !== '')
    && weights.every(value => Number.isFinite(value) && value >= 0 && value <= 10 && Math.abs(value * 10 - Math.round(value * 10)) < 1e-8)
    && weights.reduce((a, b) => a + b, 0) > 0;
});

const fableStickyQuotaFallbackEnabled = ref(true);
const fableWeeklyUsageLimitPercent = ref('50');

/** 峰值预热表单 */
const primeEnabled = ref(true);
const primeHours = ref('4,5,6');
const primeModel = ref('claude-haiku-4-5-20251001');

/** 允许 messages[].role=system 的模型列表 */
const allowSystemRoleModels = ref('claude-opus-5-5,claude-opus-5,claude-fable-5,claude-fable-5-1,claude-opus-4-8');

/** 客户端访问策略表单 */
const claudeCodeVersionProfile = ref('2.1.293');
/** 请求画像选择方式：默认按原始 UA 适配 260/280/293。 */
const claudeCodeProfileSelectionMode = ref<'client_version' | 'account'>('client_version');
const allowedClaudeCodeVersions = ref('2.1.89-2.1.293');
const blockedClaudeCodeVersions = ref('');
const allowedUserAgents = ref('AI-Hub-Monitor*\npython-httpx*');

/** Claude Code 上下文风险控制模式 */
const claudeCodeContextSanitizerMode = ref<'off' | 'report_only' | 'normalize'>('report_only');

/** 系统提示词环境字段「真值透传」开关(工作目录默认透传) */
const passthroughShell = ref(false);
const passthroughOsVersion = ref(false);
const passthroughWorkingDir = ref(true);

/** Anthropic cache_control TTL 改写模式 */
const cacheControlTtlRewrite = ref<'off' | '5m' | '1h'>('off');

/** Claude Code messages 缓存断点改写模式 */
const messageCacheControlRewrite = ref<'off' | 'auto' | 'rolling' | 'stateful' | 'sub2api'>('off');

/** API mimicry /v1/messages 顶层字段顺序指纹对齐开关 */
const messageBodyOrderFingerprintEnabled = ref(true);

/** Messages 固定根字段清理开关 */
const messageTopFieldFilterEnabled = ref(true);

/** thinking.type=disabled 兼容改写配置 */
const rewriteDisabledThinkingEnabled = ref(false);
const rewriteDisabledThinkingModels = ref('claude-fable-5');

/** assistant prefill 本地拦截配置 */
const interceptAssistantPrefillEnabled = ref(false);
const interceptAssistantPrefillModels = ref('claude-fable-5,claude-opus-5,claude-opus-4-8,claude-opus-4-7');

/** 429 请求观测日志配置 */
const log429RequestEnabled = ref(false);
const logNonStreamRequestEnabled = ref(false);
const nonStreamProbeCacheEnabled = ref(false);
const log429RequestBodyLimit = ref('8192');
const streamKeepaliveEnabled = ref(false);
const streamKeepaliveIntervalSecs = ref('45');
const streamUpstreamIdleTimeoutSecs = ref('120');

/** Claude Code bootstrap 模型选项配置 */
const bootstrapModelOptionsMode = ref<'passthrough' | 'configured' | 'hide_fable'>('passthrough');
const bootstrapAdditionalModelOptions = ref('[{"model":"claude-fable-5-1[1m]","name":"Fable","description":"Most capable for your hardest and longest-running tasks","disabled_reason":null}]');

type AutoModeClassifierMode = 'passthrough' | 'mock_allow' | 'mock_block' | 'error';
type CliBgStatusClassifierMode = 'passthrough' | 'mock';
const defaultCliBgStatusClassifierModels = 'claude-fable-5,claude-fable-5-1,claude-opus-5,claude-opus-5-5,claude-opus-4-8,claude-opus-4-7,claude-sonnet-5';

/** 代理 HTTP 客户端连接池复用开关 */
const proxyClientPoolEnabled = ref(true);

/** 有效上游 Session 首次 Hello 代理探测配置 */
const sessionHelloProbeEnabled = ref(false);
const sessionHelloProbeStrict = ref(false);
const sessionHelloProbeTimeoutSecs = ref('5');
const sessionHelloProbeSuccessTtlSecs = ref('3600');
const sessionHelloProbeFailureCooldownSecs = ref('300');

/** 预热与 Auto Mode classifier 本地处理开关 */
const interceptWarmupTitleEnabled = ref(false);
const interceptWarmupSuggestionEnabled = ref(false);
const interceptWarmupHaikuProbeEnabled = ref(false);
const interceptAutoModeClassifierStage1Mode = ref<AutoModeClassifierMode>('passthrough');
const interceptAutoModeClassifierStage2Mode = ref<AutoModeClassifierMode>('passthrough');
const interceptCliBgStatusClassifierMode = ref<CliBgStatusClassifierMode>('passthrough');
const interceptCliBgStatusClassifierModels = ref(defaultCliBgStatusClassifierModels);
const interceptCliBgStatusClassifierIdentityInjectionEnabled = ref(false);

/** 预热历史记录 */
const primeLogs = ref<PrimeLogEntry[]>([]);
const logsLoading = ref(false);

const requestDiagnosticsMode = ref('info');
const saving = ref(false);
const loaded = ref(false);

/** 将 number input 或历史响应带来的非字符串值统一成表单字符串。 */
function formString(value: unknown): string {
  if (value == null) return '';
  return typeof value === 'string' ? value : String(value);
}

/** 读取表单字符串并去掉首尾空白，避免对 number 直接调用 trim。 */
function trimFormString(value: unknown): string {
  return formString(value).trim();
}

interface ClaudeCodeVersionProfileOption {
  key: string;
  version: string;
  version_base?: string;
  build_time: string;
  allowed_claude_code_versions: string;
  growthbook_user_agent: string;
  telemetry_shape: string;
}

/** Claude Code 版本画像选项 */
const claudeCodeVersionProfiles = ref<ClaudeCodeVersionProfileOption[]>([
  {
    key: '2.1.293',
    version: '2.1.293',
    version_base: '2.1.293',
    build_time: '2026-10-07T06:36:42Z',
    allowed_claude_code_versions: '2.1.89-2.1.293',
    growthbook_user_agent: 'Bun/1.4.3',
    telemetry_shape: 'claude_code_2_1_185',
  },
  {
    key: '2.1.280',
    version: '2.1.280',
    version_base: '2.1.280',
    build_time: '2026-09-21T20:40:17Z',
    allowed_claude_code_versions: '2.1.89-2.1.280',
    growthbook_user_agent: 'Bun/1.4.3',
    telemetry_shape: 'claude_code_2_1_185',
  },
  {
    key: '2.1.260',
    version: '2.1.260',
    version_base: '2.1.260',
    build_time: '2026-09-03T19:41:35Z',
    allowed_claude_code_versions: '2.1.89-2.1.260',
    growthbook_user_agent: 'Bun/1.4.1',
    telemetry_shape: 'claude_code_2_1_185',
  },
  {
    key: '2.1.257',
    version: '2.1.257',
    version_base: '2.1.257',
    build_time: '2026-09-01T05:28:54Z',
    allowed_claude_code_versions: '2.1.89-2.1.257',
    growthbook_user_agent: 'Bun/1.4.1',
    telemetry_shape: 'claude_code_2_1_185',
  },
  {
    key: '2.1.220',
    version: '2.1.220',
    version_base: '2.1.220',
    build_time: '2026-07-24T22:17:45Z',
    allowed_claude_code_versions: '2.1.89-2.1.220',
    growthbook_user_agent: 'Bun/1.4.0',
    telemetry_shape: 'claude_code_2_1_185',
  },
  {
    key: '2.1.197',
    version: '2.1.197',
    version_base: '2.1.197',
    build_time: '2026-06-29T19:08:42Z',
    allowed_claude_code_versions: '2.1.89-2.1.197',
    growthbook_user_agent: 'Bun/1.4.0',
    telemetry_shape: 'claude_code_2_1_185',
  },
  {
    key: '2.1.195',
    version: '2.1.195',
    version_base: '2.1.195',
    build_time: '2026-06-26T01:00:56Z',
    allowed_claude_code_versions: '2.1.89-2.1.195',
    growthbook_user_agent: 'Bun/1.4.0',
    telemetry_shape: 'claude_code_2_1_185',
  },
  {
    key: '2.1.187',
    version: '2.1.187',
    version_base: '2.1.187',
    build_time: '2026-06-23T16:59:46Z',
    allowed_claude_code_versions: '2.1.89-2.1.187',
    growthbook_user_agent: 'Bun/1.4.0',
    telemetry_shape: 'claude_code_2_1_185',
  },
  {
    key: '2.1.185',
    version: '2.1.185',
    version_base: '2.1.185',
    build_time: '2026-06-20T06:38:30Z',
    allowed_claude_code_versions: '2.1.89-2.1.185',
    growthbook_user_agent: 'Bun/1.4.0',
    telemetry_shape: 'claude_code_2_1_185',
  },
  {
    key: '2.1.173',
    version: '2.1.173',
    version_base: '2.1.173',
    build_time: '2026-06-11T01:23:13Z',
    allowed_claude_code_versions: '2.1.89-2.1.173',
    growthbook_user_agent: 'Bun/1.3.14',
    telemetry_shape: 'claude_code_2_1_173',
  },
]);

/** 权重总和 */
const totalWeight = computed(() => {
  return parseFloat(formString(w7d.value) || '0') + parseFloat(formString(w5h.value) || '0') + parseFloat(formString(wconc.value) || '0');
});

/** 单个权重是否合法（非负有限数） */
function isValidWeight(v: unknown): boolean {
  const n = parseFloat(formString(v));
  return !isNaN(n) && isFinite(n) && n >= 0;
}

/** 所有权重是否合法 */
const allValid = computed(() => {
  return isValidWeight(w7d.value) && isValidWeight(w5h.value) && isValidWeight(wconc.value);
});

/** Fable 周用量百分比上限是否合法 */
const isValidFableWeeklyUsageLimitPercent = computed(() => {
  const raw = trimFormString(fableWeeklyUsageLimitPercent.value);
  if (!/^\d+$/.test(raw)) return false;
  const value = Number(raw);
  return Number.isSafeInteger(value) && value >= 1 && value <= 100;
});

/** 总和是否为 1.0 */
const isValidTotal = computed(() => {
  return Math.abs(totalWeight.value - 1.0) < 0.001;
});

/** 解析 Auto Mode classifier 本地处理模式 */
function parseAutoModeClassifierMode(raw: string | undefined): AutoModeClassifierMode {
  if (raw === 'mock_allow' || raw === 'mock_block' || raw === 'error') {
    return raw;
  }
  return 'passthrough';
}

/** 解析后端返回的 Claude Code 版本画像列表 */
function parseClaudeCodeVersionProfiles(raw: string | undefined): ClaudeCodeVersionProfileOption[] {
  if (!raw) return claudeCodeVersionProfiles.value;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return claudeCodeVersionProfiles.value;
    const options = parsed
      .map((item) => item as Partial<ClaudeCodeVersionProfileOption>)
      .filter((item) => {
        return typeof item.key === 'string'
          && typeof item.version === 'string'
          && typeof item.build_time === 'string'
          && typeof item.allowed_claude_code_versions === 'string'
          && typeof item.growthbook_user_agent === 'string'
          && typeof item.telemetry_shape === 'string';
      })
      .map((item) => ({
        key: item.key as string,
        version: item.version as string,
        version_base: item.version_base,
        build_time: item.build_time as string,
        allowed_claude_code_versions: item.allowed_claude_code_versions as string,
        growthbook_user_agent: item.growthbook_user_agent as string,
        telemetry_shape: item.telemetry_shape as string,
      }));
    return options.length > 0 ? options : claudeCodeVersionProfiles.value;
  } catch {
    return claudeCodeVersionProfiles.value;
  }
}

/**
 * 账号模式保持目标画像的准入范围，客户端模式保留独立配置。
 * @return 仅更新表单，不发送保存请求。
 */
function syncAccountProfileRange(): void {
  if (claudeCodeProfileSelectionMode.value !== 'account') return;
  const profile = claudeCodeVersionProfiles.value.find((item) => item.key === claudeCodeVersionProfile.value);
  if (profile) allowedClaudeCodeVersions.value = profile.allowed_claude_code_versions;
}

/**
 * 填入默认 293、仅允许 280/293 的访问策略。
 * @return 仅更新四项表单，保存后才生效。
 */
function use280293AccessPreset(): void {
  claudeCodeProfileSelectionMode.value = 'client_version';
  claudeCodeVersionProfile.value = '2.1.293';
  allowedClaudeCodeVersions.value = '2.1.89-2.1.293';
  blockedClaudeCodeVersions.value = '2.1.89-2.1.279,2.1.281-2.1.292';
}

/** 格式化 telemetry 结构标识，避免误读为当前 Claude Code 版本。 */
function formatTelemetryShape(shape: string): string {
  if (shape === 'claude_code_2_1_185') {
    return 'Telemetry 结构兼容 2.1.185';
  }
  if (shape === 'claude_code_2_1_173') {
    return 'Telemetry 结构 2.1.173';
  }
  return `Telemetry 结构 ${shape}`;
}

/** 预热小时输入是否合法(逗号分隔的 0-23,允许空) */
const isValidHours = computed(() => {
  const raw = trimFormString(primeHours.value);
  if (!raw) return true;
  return raw.split(',').every((s) => {
    const t = s.trim();
    if (!t) return true;
    const n = parseInt(t, 10);
    return !isNaN(n) && n >= 0 && n <= 23 && String(n) === t;
  });
});

/** 预热模型不能为空 */
const isValidModel = computed(() => trimFormString(primeModel.value).length > 0);

/** 系统角色模型列表是否合法 */
const isValidSystemRoleModels = computed(() => {
  const raw = trimFormString(allowSystemRoleModels.value);
  if (!raw) return true;
  return raw.split(',').every((s) => {
    const model = s.trim();
    return !model || /^[A-Za-z0-9._:-]+$/.test(model);
  });
});

/** Claude Code 版本规则列表是否合法 */
function isValidClaudeCodeVersionRules(rawValue: string): boolean {
  const raw = rawValue.trim();
  if (!raw) return true;
  return raw.split(/[,\n\r]+/).every((s) => {
    const item = s.trim();
    if (!item) return true;
    const version = '\\d+(?:\\.\\d+)*';
    const exact = new RegExp(`^${version}$`);
    const wildcard = new RegExp(`^${version}\\.\\*$`);
    const range = new RegExp(`^${version}-${version}$`);
    return exact.test(item) || wildcard.test(item) || range.test(item);
  });
}

/** Claude Code 版本范围是否合法 */
const isValidClaudeCodeVersions = computed(() => isValidClaudeCodeVersionRules(allowedClaudeCodeVersions.value));

/** 禁止的 Claude Code 版本范围是否合法 */
const isValidBlockedClaudeCodeVersions = computed(() => isValidClaudeCodeVersionRules(blockedClaudeCodeVersions.value));

/** UA pattern 列表是否合法 */
const isValidAllowedUserAgents = computed(() => {
  const raw = trimFormString(allowedUserAgents.value);
  if (!raw) return true;
  return raw.split(/[,\n\r]+/).every((s) => {
    const pattern = s.trim();
    return !pattern || /^[\x20-\x7E]+$/.test(pattern);
  });
});

/** thinking.type=disabled 改写模型列表是否合法 */
const isValidRewriteDisabledThinkingModels = computed(() => {
  const raw = trimFormString(rewriteDisabledThinkingModels.value);
  if (!raw) return true;
  return raw.split(',').every((s) => {
    const model = s.trim();
    return !model || /^[A-Za-z0-9._:-]+$/.test(model);
  });
});

/** assistant prefill 拦截模型列表是否合法 */
const isValidInterceptAssistantPrefillModels = computed(() => {
  const raw = trimFormString(interceptAssistantPrefillModels.value);
  if (!raw) return true;
  return raw.split(',').every((s) => {
    const model = s.trim();
    return !model || /^[A-Za-z0-9._:-]+$/.test(model);
  });
});

/** 后台状态分类本地模拟模型列表是否合法 */
const isValidInterceptCliBgStatusClassifierModels = computed(() => {
  const raw = trimFormString(interceptCliBgStatusClassifierModels.value);
  if (!raw) return true;
  return raw.split(',').every((s) => {
    const model = s.trim();
    return !model || /^[A-Za-z0-9._:-]+$/.test(model);
  });
});

/** 429 请求体日志字符上限是否合法 */
const isValidLog429RequestBodyLimit = computed(() => {
  const raw = trimFormString(log429RequestBodyLimit.value);
  if (!/^\d+$/.test(raw)) return false;
  const n = Number(raw);
  return Number.isSafeInteger(n) && n >= 0 && n <= 1048576;
});

/** 流式 keep-alive 间隔是否合法 */
const isValidStreamKeepaliveIntervalSecs = computed(() => {
  const raw = trimFormString(streamKeepaliveIntervalSecs.value);
  if (!/^\d+$/.test(raw)) return false;
  const n = Number(raw);
  return Number.isSafeInteger(n) && n >= 5 && n <= 240;
});

/** 上游流静默超时是否合法 */
const isValidStreamUpstreamIdleTimeoutSecs = computed(() => {
  const raw = trimFormString(streamUpstreamIdleTimeoutSecs.value);
  if (!/^\d+$/.test(raw)) return false;
  const n = Number(raw);
  return Number.isSafeInteger(n) && n >= 30 && n <= 1800;
});

/** Session Hello 探测超时是否合法 */
const isValidSessionHelloProbeTimeoutSecs = computed(() => {
  const raw = trimFormString(sessionHelloProbeTimeoutSecs.value);
  if (!/^\d+$/.test(raw)) return false;
  const n = Number(raw);
  return Number.isSafeInteger(n) && n >= 1 && n <= 30;
});

/** Session Hello 成功状态 TTL 是否合法 */
const isValidSessionHelloProbeSuccessTtlSecs = computed(() => {
  const raw = trimFormString(sessionHelloProbeSuccessTtlSecs.value);
  if (!/^\d+$/.test(raw)) return false;
  const n = Number(raw);
  return Number.isSafeInteger(n) && n >= 60 && n <= 86400;
});

/** Session Hello 失败冷却是否设置在支持范围内 */
const isValidSessionHelloProbeFailureCooldownSecs = computed(() => {
  const raw = trimFormString(sessionHelloProbeFailureCooldownSecs.value);
  if (!/^\d+$/.test(raw)) return false;
  const n = Number(raw);
  return Number.isSafeInteger(n) && n >= 10 && n <= 3600;
});

/** bootstrap 模型选项 JSON 是否合法 */
const isValidBootstrapAdditionalModelOptions = computed(() => {
  const raw = trimFormString(bootstrapAdditionalModelOptions.value);
  if (!raw) return true;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return false;
    return parsed.every((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) return false;
      const model = (item as Record<string, unknown>).model;
      return typeof model === 'string' && model.length > 0 && /^[A-Za-z0-9._:\-[\]]+$/.test(model);
    });
  } catch {
    return false;
  }
});

/** 加载设置 */
async function loadSettings() {
  try {
    const data = await api.getSettings();
    w7d.value = data.score_weight_7d ?? '0.5';
    w5h.value = data.score_weight_5h ?? '0.3';
    wconc.value = data.score_weight_concurrency ?? '0.2';
    v3Mode.value = data.v3_scheduling_mode ?? 'smart';
    v3WaitSeconds.value = data.v3_admission_wait_seconds ?? '120';
    v3Weights.value = [data.v3_smart_weight_load ?? '1', data.v3_smart_weight_quota ?? '0.8', data.v3_smart_weight_health ?? '1', data.v3_smart_weight_latency ?? '0.5'];

    fableStickyQuotaFallbackEnabled.value = (data.fable_sticky_quota_fallback_enabled ?? 'true') === 'true';
    fableWeeklyUsageLimitPercent.value = data.fable_weekly_usage_limit_percent ?? '50';
    primeEnabled.value = (data.peak_prime_enabled ?? 'true') === 'true';
    primeHours.value = data.peak_prime_hours ?? '4,5,6';
    primeModel.value = data.peak_prime_model ?? 'claude-haiku-4-5-20251001';
    allowSystemRoleModels.value = data.allow_system_role_models ?? 'claude-opus-5-5,claude-opus-5,claude-fable-5,claude-fable-5-1,claude-opus-4-8';
    claudeCodeVersionProfiles.value = parseClaudeCodeVersionProfiles(data.claude_code_version_profiles);
    claudeCodeVersionProfile.value = data.claude_code_version_profile ?? '2.1.293';
    claudeCodeProfileSelectionMode.value = data.claude_code_profile_selection_mode === 'account' ? 'account' : 'client_version';
    allowedClaudeCodeVersions.value = data.allowed_claude_code_versions ?? '2.1.89-2.1.293';
    blockedClaudeCodeVersions.value = data.blocked_claude_code_versions ?? '';
    allowedUserAgents.value = data.allowed_user_agents ?? 'AI-Hub-Monitor*\npython-httpx*';
    const contextSanitizerMode = data.claude_code_context_sanitizer_mode ?? 'report_only';
    claudeCodeContextSanitizerMode.value = contextSanitizerMode === 'off' || contextSanitizerMode === 'normalize' ? contextSanitizerMode : 'report_only';
    passthroughShell.value = (data.passthrough_shell ?? 'false') === 'true';
    passthroughOsVersion.value = (data.passthrough_os_version ?? 'false') === 'true';
    passthroughWorkingDir.value = (data.passthrough_working_dir ?? 'true') === 'true';
    const ttlRewrite = data.cache_control_ttl_rewrite ?? 'off';
    cacheControlTtlRewrite.value = ttlRewrite === '5m' || ttlRewrite === '1h' ? ttlRewrite : 'off';
    const messageCacheRewrite = data.message_cache_control_rewrite ?? 'off';
    if (messageCacheRewrite === 'auto' || messageCacheRewrite === 'rolling' || messageCacheRewrite === 'stateful' || messageCacheRewrite === 'sub2api') {
      messageCacheControlRewrite.value = messageCacheRewrite;
    } else if (messageCacheRewrite === 'stable' || messageCacheRewrite === 'anchored') {
      messageCacheControlRewrite.value = 'auto';
    } else {
      messageCacheControlRewrite.value = 'off';
    }
    messageBodyOrderFingerprintEnabled.value = (data.message_body_order_fingerprint_enabled ?? 'true') === 'true';
    messageTopFieldFilterEnabled.value = data.message_top_field_filter_enabled !== 'false';
    proxyClientPoolEnabled.value = (data.proxy_client_pool_enabled ?? 'true') === 'true';
    sessionHelloProbeEnabled.value = (data.session_hello_probe_enabled ?? 'false') === 'true';
    sessionHelloProbeStrict.value = (data.session_hello_probe_strict ?? 'false') === 'true';
    sessionHelloProbeTimeoutSecs.value = data.session_hello_probe_timeout_secs ?? '5';
    sessionHelloProbeSuccessTtlSecs.value = data.session_hello_probe_success_ttl_secs ?? '3600';
    sessionHelloProbeFailureCooldownSecs.value = data.session_hello_probe_failure_cooldown_secs ?? '300';
    rewriteDisabledThinkingEnabled.value = (data.rewrite_disabled_thinking_enabled ?? 'false') === 'true';
    rewriteDisabledThinkingModels.value = data.rewrite_disabled_thinking_models ?? 'claude-fable-5';
    interceptAssistantPrefillEnabled.value = (data.intercept_assistant_prefill_enabled ?? 'false') === 'true';
    interceptAssistantPrefillModels.value = data.intercept_assistant_prefill_models ?? 'claude-fable-5,claude-opus-5,claude-opus-4-8,claude-opus-4-7';
    log429RequestEnabled.value = (data.log_429_request_enabled ?? 'false') === 'true';
    logNonStreamRequestEnabled.value = (data.log_non_stream_request_enabled ?? 'false') === 'true';
    nonStreamProbeCacheEnabled.value = (data.non_stream_probe_cache_enabled ?? 'false') === 'true';
    log429RequestBodyLimit.value = data.log_429_request_body_limit ?? '8192';
    streamKeepaliveEnabled.value = (data.stream_keepalive_enabled ?? 'false') === 'true';
    streamKeepaliveIntervalSecs.value = data.stream_keepalive_interval_secs ?? '45';
    streamUpstreamIdleTimeoutSecs.value = data.stream_upstream_idle_timeout_secs ?? '120';
    const bootstrapMode = data.bootstrap_model_options_mode ?? 'passthrough';
    bootstrapModelOptionsMode.value = bootstrapMode === 'configured' || bootstrapMode === 'hide_fable' ? bootstrapMode : 'passthrough';
    bootstrapAdditionalModelOptions.value = data.bootstrap_additional_model_options ?? '[{"model":"claude-fable-5-1[1m]","name":"Fable","description":"Most capable for your hardest and longest-running tasks","disabled_reason":null}]';
    interceptWarmupTitleEnabled.value = (data.intercept_warmup_title_enabled ?? 'false') === 'true';
    interceptWarmupSuggestionEnabled.value = (data.intercept_warmup_suggestion_enabled ?? 'false') === 'true';
    interceptWarmupHaikuProbeEnabled.value = (data.intercept_warmup_haiku_probe_enabled ?? 'false') === 'true';
    interceptAutoModeClassifierStage1Mode.value = parseAutoModeClassifierMode(data.intercept_auto_mode_classifier_stage1_mode);
    interceptAutoModeClassifierStage2Mode.value = parseAutoModeClassifierMode(data.intercept_auto_mode_classifier_stage2_mode);
    interceptCliBgStatusClassifierMode.value = data.intercept_cli_bg_status_classifier_mode === 'mock' ? 'mock' : 'passthrough';
    interceptCliBgStatusClassifierModels.value = data.intercept_cli_bg_status_classifier_models ?? defaultCliBgStatusClassifierModels;
    interceptCliBgStatusClassifierIdentityInjectionEnabled.value =
      (data.intercept_cli_bg_status_classifier_identity_injection_enabled ?? 'false') === 'true';
    requestDiagnosticsMode.value = data.request_diagnostics_log_mode === 'debug' ? 'debug' : 'info';
    savedValues.value = readValues();
    loaded.value = true;
  } catch (e) {
    toast((e as Error).message || '加载设置失败');
  }
}

/** 加载最近预热记录 */
async function loadPrimeLogs() {
  logsLoading.value = true;
  try {
    primeLogs.value = await api.getPrimeLogs();
  } catch (e) {
    toast((e as Error).message || '加载预热记录失败');
  } finally {
    logsLoading.value = false;
  }
}

/** 保存设置 */
async function saveSettings() {
  if (!allValid.value) {
    toast('权重必须为非负数');
    return;
  }
  if (!isValidFableWeeklyUsageLimitPercent.value) {
    toast('Fable 周用量上限必须是 1 到 100 之间的整数');
    return;
  }
  if (!isValidHours.value) {
    toast('预热小时必须是逗号分隔的 0-23 整数');
    return;
  }
  if (!isValidModel.value) {
    toast('预热模型不能为空');
    return;
  }
  if (!isValidSystemRoleModels.value) {
    toast('系统角色模型列表包含非法字符');
    return;
  }
  if (!isValidClaudeCodeVersions.value) {
    toast('Claude Code 版本范围格式不正确');
    return;
  }
  if (!isValidBlockedClaudeCodeVersions.value) {
    toast('禁止 Claude Code 版本格式不正确');
    return;
  }
  if (!isValidAllowedUserAgents.value) {
    toast('UA 白名单包含非法字符');
    return;
  }
  if (!isValidRewriteDisabledThinkingModels.value) {
    toast('thinking 改写模型列表包含非法字符');
    return;
  }
  if (!isValidInterceptAssistantPrefillModels.value) {
    toast('assistant prefill 拦截模型列表包含非法字符');
    return;
  }
  if (!isValidInterceptCliBgStatusClassifierModels.value) {
    toast('后台状态分类模型列表包含非法字符');
    return;
  }
  if (!isValidLog429RequestBodyLimit.value) {
    toast('429 请求体日志上限必须是 0 到 1048576 的整数');
    return;
  }
  if (!isValidStreamKeepaliveIntervalSecs.value) {
    toast('流式 keep-alive 间隔必须是 5 到 240 秒的整数');
    return;
  }
  if (!isValidStreamUpstreamIdleTimeoutSecs.value) {
    toast('上游流静默超时必须是 30 到 1800 秒的整数');
    return;
  }
  if (!isValidSessionHelloProbeTimeoutSecs.value) {
    toast('Session Hello 探测超时必须是 1 到 30 秒的整数');
    return;
  }
  if (!isValidSessionHelloProbeSuccessTtlSecs.value) {
    toast('Session Hello 成功 TTL 必须是 60 到 86400 秒的整数');
    return;
  }
  if (!isValidSessionHelloProbeFailureCooldownSecs.value) {
    toast('Session Hello 失败冷却必须是 10 到 3600 秒的整数');
    return;
  }
  if (!isValidBootstrapAdditionalModelOptions.value) {
    toast('bootstrap 模型选项必须是 JSON 数组,且每项包含合法 model');
    return;
  }
  if (!isValidV3.value) {
    toast('flower2api 等待上限须为 1–120 秒；权重须为 0–10、最多一位小数，且不能全部为零');
    return;
  }
  saving.value = true;
  try {
    const snapshot = readValues();
    await api.updateSettings(snapshot);
    savedValues.value = snapshot;
    toast('保存成功','success');
  } catch (e) {
    toast((e as Error).message || '保存失败');
  } finally {
    saving.value = false;
  }
}

/** 格式化时间戳 */
function formatTime(raw: string): string {
  if (!raw) return '-';
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/** 判断一条日志是否"跳过"而非真正失败。
 *  后端把冷却期跳过统一用 'skipped: ...' 前缀写入 error_message,
 *  前端依前缀识别,渲染成琥珀色"跳过"徽章,避免与红色"失败"混淆。 */
function isSkipped(log: PrimeLogEntry): boolean {
  return !log.success && log.error_message.startsWith('skipped:');
}


/** 表单字段直接关联既有状态；所有提交值保持字符串。 */
const fieldBindings: Record<string, {get: () => string;set: (value: string) => void}> = {
  score_weight_7d: { get: () => formString(String(w7d.value)), set: value => { w7d.value = value as typeof w7d.value; } },
  score_weight_5h: { get: () => formString(String(w5h.value)), set: value => { w5h.value = value as typeof w5h.value; } },
  score_weight_concurrency: { get: () => formString(String(wconc.value)), set: value => { wconc.value = value as typeof wconc.value; } },
  v3_scheduling_mode: { get: () => formString(v3Mode.value), set: value => { v3Mode.value = value as typeof v3Mode.value; } },
  v3_admission_wait_seconds: { get: () => formString(String(v3WaitSeconds.value).trim()), set: value => { v3WaitSeconds.value = value as typeof v3WaitSeconds.value; } },
  v3_smart_weight_load: { get: () => formString(String(v3Weights.value[0]).trim()), set: value => { v3Weights.value[0] = value as typeof v3Weights.value[0]; } },
  v3_smart_weight_quota: { get: () => formString(String(v3Weights.value[1]).trim()), set: value => { v3Weights.value[1] = value as typeof v3Weights.value[1]; } },
  v3_smart_weight_health: { get: () => formString(String(v3Weights.value[2]).trim()), set: value => { v3Weights.value[2] = value as typeof v3Weights.value[2]; } },
  v3_smart_weight_latency: { get: () => formString(String(v3Weights.value[3]).trim()), set: value => { v3Weights.value[3] = value as typeof v3Weights.value[3]; } },
  fable_sticky_quota_fallback_enabled: { get: () => formString(fableStickyQuotaFallbackEnabled.value ? 'true' : 'false'), set: value => { fableStickyQuotaFallbackEnabled.value = value === 'true'; } },
  fable_weekly_usage_limit_percent: { get: () => formString(trimFormString(fableWeeklyUsageLimitPercent.value)), set: value => { fableWeeklyUsageLimitPercent.value = value as typeof fableWeeklyUsageLimitPercent.value; } },
  peak_prime_enabled: { get: () => formString(primeEnabled.value ? 'true' : 'false'), set: value => { primeEnabled.value = value === 'true'; } },
  peak_prime_hours: { get: () => formString(trimFormString(primeHours.value)), set: value => { primeHours.value = value as typeof primeHours.value; } },
  peak_prime_model: { get: () => formString(trimFormString(primeModel.value)), set: value => { primeModel.value = value as typeof primeModel.value; } },
  allow_system_role_models: { get: () => formString(trimFormString(allowSystemRoleModels.value)), set: value => { allowSystemRoleModels.value = value as typeof allowSystemRoleModels.value; } },
  claude_code_version_profile: { get: () => formString(claudeCodeVersionProfile.value), set: value => { claudeCodeVersionProfile.value = value as typeof claudeCodeVersionProfile.value; } },
  claude_code_profile_selection_mode: { get: () => formString(claudeCodeProfileSelectionMode.value), set: value => { claudeCodeProfileSelectionMode.value = value as typeof claudeCodeProfileSelectionMode.value; } },
  allowed_claude_code_versions: { get: () => formString(trimFormString(allowedClaudeCodeVersions.value)), set: value => { allowedClaudeCodeVersions.value = value as typeof allowedClaudeCodeVersions.value; } },
  blocked_claude_code_versions: { get: () => formString(trimFormString(blockedClaudeCodeVersions.value)), set: value => { blockedClaudeCodeVersions.value = value as typeof blockedClaudeCodeVersions.value; } },
  allowed_user_agents: { get: () => formString(trimFormString(allowedUserAgents.value)), set: value => { allowedUserAgents.value = value as typeof allowedUserAgents.value; } },
  claude_code_context_sanitizer_mode: { get: () => formString(claudeCodeContextSanitizerMode.value), set: value => { claudeCodeContextSanitizerMode.value = value as typeof claudeCodeContextSanitizerMode.value; } },
  passthrough_shell: { get: () => formString(passthroughShell.value ? 'true' : 'false'), set: value => { passthroughShell.value = value === 'true'; } },
  passthrough_os_version: { get: () => formString(passthroughOsVersion.value ? 'true' : 'false'), set: value => { passthroughOsVersion.value = value === 'true'; } },
  passthrough_working_dir: { get: () => formString(passthroughWorkingDir.value ? 'true' : 'false'), set: value => { passthroughWorkingDir.value = value === 'true'; } },
  cache_control_ttl_rewrite: { get: () => formString(cacheControlTtlRewrite.value), set: value => { cacheControlTtlRewrite.value = value as typeof cacheControlTtlRewrite.value; } },
  message_cache_control_rewrite: { get: () => formString(messageCacheControlRewrite.value), set: value => { messageCacheControlRewrite.value = value as typeof messageCacheControlRewrite.value; } },
  message_body_order_fingerprint_enabled: { get: () => formString(messageBodyOrderFingerprintEnabled.value ? 'true' : 'false'), set: value => { messageBodyOrderFingerprintEnabled.value = value === 'true'; } },
  message_top_field_filter_enabled: { get: () => formString(messageTopFieldFilterEnabled.value ? 'true' : 'false'), set: value => { messageTopFieldFilterEnabled.value = value === 'true'; } },
  proxy_client_pool_enabled: { get: () => formString(proxyClientPoolEnabled.value ? 'true' : 'false'), set: value => { proxyClientPoolEnabled.value = value === 'true'; } },
  session_hello_probe_enabled: { get: () => formString(sessionHelloProbeEnabled.value ? 'true' : 'false'), set: value => { sessionHelloProbeEnabled.value = value === 'true'; } },
  session_hello_probe_strict: { get: () => formString(sessionHelloProbeStrict.value ? 'true' : 'false'), set: value => { sessionHelloProbeStrict.value = value === 'true'; } },
  session_hello_probe_timeout_secs: { get: () => formString(trimFormString(sessionHelloProbeTimeoutSecs.value)), set: value => { sessionHelloProbeTimeoutSecs.value = value as typeof sessionHelloProbeTimeoutSecs.value; } },
  session_hello_probe_success_ttl_secs: { get: () => formString(trimFormString(sessionHelloProbeSuccessTtlSecs.value)), set: value => { sessionHelloProbeSuccessTtlSecs.value = value as typeof sessionHelloProbeSuccessTtlSecs.value; } },
  session_hello_probe_failure_cooldown_secs: { get: () => formString(trimFormString(sessionHelloProbeFailureCooldownSecs.value)), set: value => { sessionHelloProbeFailureCooldownSecs.value = value as typeof sessionHelloProbeFailureCooldownSecs.value; } },
  rewrite_disabled_thinking_enabled: { get: () => formString(rewriteDisabledThinkingEnabled.value ? 'true' : 'false'), set: value => { rewriteDisabledThinkingEnabled.value = value === 'true'; } },
  rewrite_disabled_thinking_models: { get: () => formString(trimFormString(rewriteDisabledThinkingModels.value)), set: value => { rewriteDisabledThinkingModels.value = value as typeof rewriteDisabledThinkingModels.value; } },
  intercept_assistant_prefill_enabled: { get: () => formString(interceptAssistantPrefillEnabled.value ? 'true' : 'false'), set: value => { interceptAssistantPrefillEnabled.value = value === 'true'; } },
  intercept_assistant_prefill_models: { get: () => formString(trimFormString(interceptAssistantPrefillModels.value)), set: value => { interceptAssistantPrefillModels.value = value as typeof interceptAssistantPrefillModels.value; } },
  log_429_request_enabled: { get: () => formString(log429RequestEnabled.value ? 'true' : 'false'), set: value => { log429RequestEnabled.value = value === 'true'; } },
  log_non_stream_request_enabled: { get: () => formString(logNonStreamRequestEnabled.value ? 'true' : 'false'), set: value => { logNonStreamRequestEnabled.value = value === 'true'; } },
  non_stream_probe_cache_enabled: { get: () => formString(nonStreamProbeCacheEnabled.value ? 'true' : 'false'), set: value => { nonStreamProbeCacheEnabled.value = value === 'true'; } },
  log_429_request_body_limit: { get: () => formString(trimFormString(log429RequestBodyLimit.value)), set: value => { log429RequestBodyLimit.value = value as typeof log429RequestBodyLimit.value; } },
  stream_keepalive_enabled: { get: () => formString(streamKeepaliveEnabled.value ? 'true' : 'false'), set: value => { streamKeepaliveEnabled.value = value === 'true'; } },
  stream_keepalive_interval_secs: { get: () => formString(trimFormString(streamKeepaliveIntervalSecs.value)), set: value => { streamKeepaliveIntervalSecs.value = value as typeof streamKeepaliveIntervalSecs.value; } },
  stream_upstream_idle_timeout_secs: { get: () => formString(trimFormString(streamUpstreamIdleTimeoutSecs.value)), set: value => { streamUpstreamIdleTimeoutSecs.value = value as typeof streamUpstreamIdleTimeoutSecs.value; } },
  bootstrap_model_options_mode: { get: () => formString(bootstrapModelOptionsMode.value), set: value => { bootstrapModelOptionsMode.value = value as typeof bootstrapModelOptionsMode.value; } },
  bootstrap_additional_model_options: { get: () => formString(trimFormString(bootstrapAdditionalModelOptions.value)), set: value => { bootstrapAdditionalModelOptions.value = value as typeof bootstrapAdditionalModelOptions.value; } },
  intercept_warmup_title_enabled: { get: () => formString(interceptWarmupTitleEnabled.value ? 'true' : 'false'), set: value => { interceptWarmupTitleEnabled.value = value === 'true'; } },
  intercept_warmup_suggestion_enabled: { get: () => formString(interceptWarmupSuggestionEnabled.value ? 'true' : 'false'), set: value => { interceptWarmupSuggestionEnabled.value = value === 'true'; } },
  intercept_warmup_haiku_probe_enabled: { get: () => formString(interceptWarmupHaikuProbeEnabled.value ? 'true' : 'false'), set: value => { interceptWarmupHaikuProbeEnabled.value = value === 'true'; } },
  intercept_auto_mode_classifier_stage1_mode: { get: () => formString(interceptAutoModeClassifierStage1Mode.value), set: value => { interceptAutoModeClassifierStage1Mode.value = value as typeof interceptAutoModeClassifierStage1Mode.value; } },
  intercept_auto_mode_classifier_stage2_mode: { get: () => formString(interceptAutoModeClassifierStage2Mode.value), set: value => { interceptAutoModeClassifierStage2Mode.value = value as typeof interceptAutoModeClassifierStage2Mode.value; } },
  intercept_cli_bg_status_classifier_mode: { get: () => formString(interceptCliBgStatusClassifierMode.value), set: value => { interceptCliBgStatusClassifierMode.value = value as typeof interceptCliBgStatusClassifierMode.value; } },
  intercept_cli_bg_status_classifier_models: { get: () => formString(trimFormString(interceptCliBgStatusClassifierModels.value)), set: value => { interceptCliBgStatusClassifierModels.value = value as typeof interceptCliBgStatusClassifierModels.value; } },
  intercept_cli_bg_status_classifier_identity_injection_enabled: { get: () => formString(interceptCliBgStatusClassifierIdentityInjectionEnabled.value ? 'true' : 'false'), set: value => { interceptCliBgStatusClassifierIdentityInjectionEnabled.value = value === 'true'; } },
  request_diagnostics_log_mode: {get: () => requestDiagnosticsMode.value, set: value => {requestDiagnosticsMode.value = value;}},
};
const savedValues = ref<Record<string,string>>({});
const settingsQuery = ref('');
const settingsCategory = ref('scheduling');
const fieldErrors = ref<Record<string,string>>({});
const groupIcons = {scheduling:Activity,models:Box,access:ShieldCheck,connections:Globe,warmup:Settings2,observability:FileText,history:Clock};
const allFields = settingsGroups.flatMap(group=>group.sections.flatMap(section=>section.fields));
const dirtyKeys = computed(()=>allFields.filter(field=>fieldBindings[field.key]?.get() !== savedValues.value[field.key]).map(field=>field.key));
const currentGroup = computed(()=>settingsGroups.find(group=>group.id===settingsCategory.value)!);
const visibleGroups = computed(()=>settingsGroups.filter(group=>settingsQuery.value.trim() || group.id===settingsCategory.value).map(group=>({...group,sections:group.sections.map(section=>({...section,fields:section.fields.filter(field=>!settingsQuery.value.trim() || `${field.label} ${field.help} ${field.key} ${section.title} ${group.label}`.toLowerCase().includes(settingsQuery.value.trim().toLowerCase()))})).filter(section=>section.fields.length)})).filter(group=>group.sections.length));
/** 冻结当前提交内容，保存期间的新修改继续留在草稿。@return 字符串设置快照。 */
function readValues(): Record<string,string> {return Object.fromEntries(Object.entries(fieldBindings).map(([key,binding])=>[key,binding.get()]));}
/** 写入字段并维护原画像联动。@param key 配置键。@param value 输入。@return 无。 */
function updateField(key:string,value:unknown): void {
  fieldBindings[key]?.set(formString(value));delete fieldErrors.value[key];
  if(key==='claude_code_profile_selection_mode' || key==='claude_code_version_profile') syncAccountProfileRange();
}
/** 撤销至最近保存的快照。@return 无。 */
function revertChanges(): void {for(const [key,value] of Object.entries(savedValues.value))fieldBindings[key]?.set(value);fieldErrors.value={};}
/** 切换分类保留草稿。@param id 分类。@return 无。 */
function chooseCategory(id:string):void {settingsCategory.value=id;settingsQuery.value='';}
/** 根据真实依赖禁用编辑并保留原值。@param field 配置。@return 是否禁用。 */
function disabledField(field:SettingField):boolean {
 if(field.key.startsWith('session_hello_probe_') && field.key!=='session_hello_probe_enabled')return !sessionHelloProbeEnabled.value;
 if(field.key==='intercept_cli_bg_status_classifier_identity_injection_enabled')return interceptCliBgStatusClassifierMode.value==='mock';
 return false;
}
/** 动态画像以实际接口候选为准。@param field 字段。@return 菜单候选。 */
function fieldOptions(field:SettingField):{value:string;label:string}[] {
 if(field.key==='claude_code_version_profile')return claudeCodeVersionProfiles.value.map(profile=>({value:profile.key,label:profile.version}));
 return (field.options??[]).map(([value,label])=>({value,label}));
}
/** 预设只修改草稿。@param preset 预设。@return 无。 */
function applyPreset(preset:string):void {
 if(preset==='access')use280293AccessPreset();
 if(preset==='system-default')allowSystemRoleModels.value='claude-opus-5-5,claude-opus-5,claude-fable-5,claude-fable-5-1,claude-opus-4-8';
 if(preset==='system-clear')allowSystemRoleModels.value='';
 if(preset==='agents-default')allowedUserAgents.value='AI-Hub-Monitor*\npython-httpx*';
 if(preset==='agents-clear')allowedUserAgents.value='';
}
/** 先定位实际错误，再执行原有业务校验与保存。@return 保存结束。 */
async function submitSettings():Promise<void> {
 const checks:Record<string,boolean>={score_weight_7d:allValid.value,score_weight_5h:allValid.value,score_weight_concurrency:allValid.value,v3_admission_wait_seconds:isValidV3.value,v3_smart_weight_load:isValidV3.value,fable_weekly_usage_limit_percent:isValidFableWeeklyUsageLimitPercent.value,peak_prime_hours:isValidHours.value,peak_prime_model:isValidModel.value,allow_system_role_models:isValidSystemRoleModels.value,allowed_claude_code_versions:isValidClaudeCodeVersions.value,blocked_claude_code_versions:isValidBlockedClaudeCodeVersions.value,allowed_user_agents:isValidAllowedUserAgents.value,rewrite_disabled_thinking_models:isValidRewriteDisabledThinkingModels.value,intercept_assistant_prefill_models:isValidInterceptAssistantPrefillModels.value,intercept_cli_bg_status_classifier_models:isValidInterceptCliBgStatusClassifierModels.value,log_429_request_body_limit:isValidLog429RequestBodyLimit.value,stream_keepalive_interval_secs:isValidStreamKeepaliveIntervalSecs.value,stream_upstream_idle_timeout_secs:isValidStreamUpstreamIdleTimeoutSecs.value,session_hello_probe_timeout_secs:isValidSessionHelloProbeTimeoutSecs.value,session_hello_probe_success_ttl_secs:isValidSessionHelloProbeSuccessTtlSecs.value,session_hello_probe_failure_cooldown_secs:isValidSessionHelloProbeFailureCooldownSecs.value,bootstrap_additional_model_options:isValidBootstrapAdditionalModelOptions.value};
 fieldErrors.value={};
 for(const field of allFields){const value=fieldBindings[field.key]!.get();if(checks[field.key]===false || (field.kind==='number' && (!value.trim() || !Number.isFinite(Number(value)) || (field.min!=null && Number(value)<field.min) || (field.max!=null && Number(value)>field.max))) || (field.kind==='select' && !fieldOptions(field).some(option=>option.value===value)))fieldErrors.value[field.key]='请检查此配置的格式或范围';}
 const key=Object.keys(fieldErrors.value)[0];
 if(key){settingsCategory.value=settingsGroups.find(group=>group.sections.some(section=>section.fields.some(field=>field.key===key)))!.id;settingsQuery.value='';await nextTick();document.querySelector<HTMLElement>(`[data-settings-field="${key}"] input,[data-settings-field="${key}"] textarea,[data-settings-field="${key}"] button`)?.focus();toast('请修正标出的配置项');return;}
 await saveSettings();
}

onMounted(async () => {
  await loadSettings();
  await loadPrimeLogs();
});
</script>

<template>
 <div class="settings-page">
  <div class="page-heading"><div><p class="page-eyebrow">平台配置</p><h2>系统设置</h2><p class="page-description">按用途管理网关策略，修改后统一保存。</p></div></div>
  <div class="settings-overview-bar"><SearchInput v-model="settingsQuery" label="搜索系统设置" placeholder="搜索配置名称、用途或关键词" class="settings-search" /><span>{{ allFields.length }} 项配置</span></div>
  <div class="system-settings-layout">
   <nav class="system-settings-nav" aria-label="系统设置分类"><button v-for="group in settingsGroups" :key="group.id" type="button" :class="{active:settingsCategory===group.id && !settingsQuery}" :aria-pressed="settingsCategory===group.id && !settingsQuery" @click="chooseCategory(group.id)"><component :is="groupIcons[group.id as keyof typeof groupIcons]" :size="16" /><span>{{ group.label }}</span><i v-if="group.sections.some(section=>section.fields.some(field=>dirtyKeys.includes(field.key)))" /><b v-if="group.id==='history'">{{ primeLogs.length }}</b></button><p>所有配置统一保存。<br>切换分类保留未保存内容。</p></nav>
   <div class="settings-workspace"><header class="settings-workspace-heading"><h2>{{ settingsQuery ? '搜索结果' : currentGroup.label }}</h2><p>{{ settingsQuery ? '跨分类查找，直接修改对应配置。' : currentGroup.description }}</p></header>
    <form @submit.prevent="submitSettings" novalidate><div id="settings-content">
     <p v-if="settingsQuery" class="settings-search-result">找到 {{ visibleGroups.reduce((sum,group)=>sum+group.sections.reduce((n,section)=>n+section.fields.length,0),0) }} 项配置</p>
     <template v-for="group in visibleGroups" :key="group.id"><section v-for="section in group.sections" :key="section.title" class="settings-section-card"><header><div><span v-if="settingsQuery" class="settings-result-category">{{ group.label }}</span><h3>{{ section.title }}</h3><p>{{ section.description }}</p></div><span class="settings-section-icon"><component :is="groupIcons[group.id as keyof typeof groupIcons]" :size="18" /></span></header>
      <div class="settings-field-grid"><div v-for="field in section.fields" :key="field.key" class="setting-field" :class="{wide:field.wide || field.kind==='boolean','has-error':fieldErrors[field.key]}" :data-settings-field="field.key">
       <label v-if="field.kind==='boolean'" class="setting-switch-row" :class="{'is-disabled':disabledField(field)}"><span><strong>{{ field.label }}</strong><small>{{ field.help }}</small></span><input type="checkbox" role="switch" :name="field.key" :aria-label="field.label" :checked="fieldBindings[field.key]!.get()==='true'" :disabled="disabledField(field)" @change="updateField(field.key,($event.target as HTMLInputElement).checked)"><i aria-hidden="true" /></label>
       <ChoiceSelect v-else-if="field.kind==='select'" :model-value="fieldBindings[field.key]!.get()" :name="field.key" :label="field.label" :options="fieldOptions(field)" :disabled="disabledField(field)" :invalid="!!fieldErrors[field.key]" @update:model-value="value=>updateField(field.key,value)" />
       <NumberInput v-else-if="field.kind==='number'" :model-value="fieldBindings[field.key]!.get()" :name="field.key" :label="field.label" :min="field.min" :max="field.max" :step="field.step ?? 1" :disabled="disabledField(field)" :invalid="!!fieldErrors[field.key]" @update:model-value="value=>updateField(field.key,value)" />
       <label v-else class="field"><span>{{ field.label }}</span><Textarea v-if="['textarea','json','models'].includes(field.kind)" :model-value="fieldBindings[field.key]!.get()" :name="field.key" :rows="field.kind==='json'?6:field.kind==='models'?3:4" :aria-invalid="!!fieldErrors[field.key]" spellcheck="false" @update:model-value="value=>updateField(field.key,value)" /><Input v-else :model-value="fieldBindings[field.key]!.get()" :name="field.key" :aria-invalid="!!fieldErrors[field.key]" autocomplete="off" @update:model-value="value=>updateField(field.key,value)" /></label>
       <p v-if="field.kind!=='boolean' && field.help" class="setting-help">{{ field.help }}</p>
       <div v-if="field.preset" class="setting-presets"><template v-if="field.preset==='system'"><button type="button" @click="applyPreset('system-default')">推荐模型</button><button type="button" @click="applyPreset('system-clear')">清空模型</button></template><template v-if="field.preset==='agents'"><button type="button" @click="applyPreset('agents-default')">默认 UA 白名单</button><button type="button" @click="applyPreset('agents-clear')">关闭 UA 限制</button></template><button v-if="field.preset==='access'" type="button" @click="applyPreset('access')">仅允许 280 / 293</button></div>
       <p v-if="fieldErrors[field.key]" role="alert" class="setting-error">{{ fieldErrors[field.key] }}</p>
      </div></div>
      <p v-if="section.summary==='legacy-weight'" class="settings-inline-note">当前权重总和 {{ totalWeight.toFixed(2) }} · {{ isValidTotal ? '已归一化' : '建议为 1.00' }}</p>
      <template v-if="section.summary==='profile'"><p v-for="profile in claudeCodeVersionProfiles.filter(item=>item.key===claudeCodeVersionProfile)" :key="profile.key" class="settings-inline-note">画像准入 {{ profile.allowed_claude_code_versions }} · {{ profile.growthbook_user_agent }} · {{ profile.build_time }} · {{ formatTelemetryShape(profile.telemetry_shape) }}</p></template>
     </section></template>
     <section v-if="settingsCategory==='history' && !settingsQuery" class="settings-section-card"><header><div><h3>最近预热记录</h3><p>按触发时间倒序 · 最多保留 200 条</p></div><Button type="button" variant="outline" :disabled="logsLoading" @click="loadPrimeLogs">{{ logsLoading ? '加载中…' : '刷新' }}</Button></header>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead class="text-muted-foreground">时间</TableHead>
              <TableHead class="text-muted-foreground">账号</TableHead>
              <TableHead class="text-muted-foreground">小时</TableHead>
              <TableHead class="text-muted-foreground">模型</TableHead>
              <TableHead class="text-muted-foreground">耗时</TableHead>
              <TableHead class="text-muted-foreground">结果</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="log in primeLogs" :key="log.id">
              <TableCell class="text-foreground text-xs whitespace-nowrap">{{ formatTime(log.triggered_at) }}</TableCell>
              <TableCell class="text-foreground text-xs">
                <span class="font-medium">{{ log.account_name || `#${log.account_id}` }}</span>
                <span class="text-muted-foreground ml-1">#{{ log.account_id }}</span>
              </TableCell>
              <TableCell class="text-foreground text-xs">{{ String(log.hour).padStart(2, '0') }}:10</TableCell>
              <TableCell class="text-foreground text-xs">{{ log.model }}</TableCell>
              <TableCell class="text-foreground text-xs">{{ log.duration_ms }}ms</TableCell>
              <TableCell>
                <Badge
                  v-if="log.success"
                  class="bg-emerald-50 text-emerald-700 border-emerald-200"
                >
                  成功
                </Badge>
                <Badge
                  v-else-if="isSkipped(log)"
                  class="bg-amber-50 text-amber-700 border-amber-200"
                  :title="log.error_message"
                >
                  跳过
                </Badge>
                <Badge
                  v-else
                  class="bg-red-50 text-red-700 border-red-200"
                  :title="log.error_message"
                >
                  失败
                </Badge>
                <span
                  v-if="!log.success && log.error_message"
                  class="ml-2 text-[11px] text-muted-foreground truncate inline-block max-w-[260px] align-middle"
                  :title="log.error_message"
                >
                  {{ log.error_message }}
                </span>
              </TableCell>
            </TableRow>
            <TableEmpty v-if="primeLogs.length === 0" :colspan="6">
              暂无预热记录
            </TableEmpty>
          </TableBody>
        </Table>
     </section>
     <section v-if="!visibleGroups.length && (settingsCategory!=='history' || settingsQuery)" class="settings-empty"><h3>没有匹配的配置</h3><p>试试功能名称、模型或配置关键词。</p><Button type="button" variant="outline" @click="settingsQuery=''">清空搜索</Button></section>
    </div>
    <footer class="settings-save-bar"><div><strong>{{ dirtyKeys.length ? `${dirtyKeys.length} 项待保存` : '配置已同步' }}</strong><small>修改将统一应用到网关</small></div><div class="settings-save-actions"><Button type="button" variant="outline" :disabled="!loaded || saving || !dirtyKeys.length" @click="revertChanges">撤销修改</Button><Button type="submit" :disabled="!loaded || saving || !dirtyKeys.length">{{ saving ? '保存中…' : '保存配置' }}</Button></div></footer>
    </form>
   </div>
  </div>
 </div>
</template>
