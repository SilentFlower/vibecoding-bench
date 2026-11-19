/** 系统设置元数据直接沿用已确认定稿；键集合与真实保存映射核对。 */
export interface SettingField {key:string;label:string;kind:string;help:string;options?:string[][];min?:number;max?:number;step?:number;wide?:boolean;preset?:string;nonnegative?:boolean;validation?:string;enabledWhen?:string[];disabledWhen?:string[];required?:boolean;}
/** 配置分类与独立段落。 */
export interface SettingsGroup {id:string;label:string;icon:string;description:string;sections:{title:string;description:string;summary?:string;fields:SettingField[]}[];}
/** 全量配置的展示合同，字段行为由 Settings.vue 维护。 */
export const settingsGroups:SettingsGroup[] = [
  {
    "id": "scheduling",
    "label": "会话与调度",
    "icon": "wave",
    "description": "新会话排序、等待期限与配额切换",
    "sections": [
      {
        "title": "会话与发送调度",
        "description": "老会话保持有效绑定，新会话根据资格与容量选择账号。",
        "fields": [
          {
            "key": "v3_admission_wait_seconds",
            "label": "准入等待上限（秒）",
            "kind": "number",
            "help": "并发、准备与发送阶段共用等待期限。",
            "min": 1,
            "max": 120
          },
          {
            "key": "v3_smart_weight_load",
            "label": "可用负载权重",
            "kind": "number",
            "help": "0–10，最多一位小数。",
            "min": 0,
            "max": 10,
            "step": 0.1
          },
          {
            "key": "v3_smart_weight_quota",
            "label": "有效额度权重",
            "kind": "number",
            "help": "0–10，最多一位小数。",
            "min": 0,
            "max": 10,
            "step": 0.1
          },
          {
            "key": "v3_smart_weight_health",
            "label": "真实健康权重",
            "kind": "number",
            "help": "0–10，最多一位小数。",
            "min": 0,
            "max": 10,
            "step": 0.1
          },
          {
            "key": "v3_smart_weight_latency",
            "label": "首输出延迟权重",
            "kind": "number",
            "help": "0–10，最多一位小数。",
            "min": 0,
            "max": 10,
            "step": 0.1
          },
          {
            "key": "v3_smart_weight_reset",
            "label": "额度重置系数",
            "kind": "number",
            "help": "0 关闭。其他条件相近时优先利用即将重置的额度。",
            "min": 0,
            "max": 10,
            "step": 0.1
          },
          {
            "key": "v3_smart_weight_queue",
            "label": "排队等待系数",
            "kind": "number",
            "help": "0 关闭。账号都需要等待时，优先选择预计等待较短的队列。",
            "min": 0,
            "max": 10,
            "step": 0.1
          },
          {
            "key": "v3_smart_reset_weight_5h",
            "label": "5 小时重置窗口权重",
            "kind": "number",
            "help": "设置 5 小时窗口在重置偏好中的贡献，0 忽略此窗口。",
            "min": 0,
            "max": 10,
            "step": 0.1
          },
          {
            "key": "v3_smart_reset_weight_7d",
            "label": "周重置窗口权重",
            "kind": "number",
            "help": "设置周窗口在重置偏好中的贡献，0 忽略此窗口。",
            "min": 0,
            "max": 10,
            "step": 0.1
          }
        ]
      },
      {
        title: '会话策略封禁', description: '会话触发明确策略拒答后，在指定时间内由本地拦截后续请求。', summary: 'session-policy-block',
        fields: [
          { key:'session_policy_block_enabled', label:'自动封禁', kind:'boolean', help:'开启后按真实客户端会话隔离，封禁及历史记录可在会话封禁页面查看。' },
          { key:'session_policy_block_duration_minutes', label:'封禁时长（分钟）', kind:'number', min:1, step:1, help:'默认 24 小时（1440 分钟）。\n修改仅影响新封禁，重复拦截保持原到期时间。' },
        ],
      },
      {
        "title": "Fable 配额切换",
        "description": "达到最近观测的周用量上限后，尝试切换其他账号。",
        "fields": [
          {
            "key": "fable_sticky_quota_fallback_enabled",
            "label": "启用配额切换",
            "kind": "boolean",
            "help": "达到上限后停止分配新的 Fable 请求，单次请求可能越线。"
          },
          {
            "key": "fable_weekly_usage_limit_percent",
            "label": "周用量上限（%）",
            "kind": "number",
            "help": "允许 1–100 的整数。",
            "min": 1,
            "max": 100
          }
        ]
      }
    ]
  },
  {
    "id": "models",
    "label": "模型与缓存",
    "icon": "box",
    "description": "模型兼容、缓存策略与请求处理",
    "sections": [
      {
        "title": "模型兼容",
        "description": "按模型范围控制请求兼容行为。",
        "fields": [
          {
            "key": "allow_system_role_models",
            "label": "允许 system 角色的模型",
            "kind": "models",
            "help": "多个完整模型名称以逗号分隔。",
            "wide": true,
            "preset": "system"
          },
          {
            "key": "rewrite_disabled_thinking_enabled",
            "label": "兼容 thinking.type=disabled",
            "kind": "boolean",
            "help": "仅对配置的模型执行兼容改写。"
          },
          {
            "key": "rewrite_disabled_thinking_models",
            "label": "thinking 改写模型",
            "kind": "models",
            "help": "留空表示没有适用模型。",
            "wide": true
          },
          {
            "key": "intercept_assistant_prefill_enabled",
            "label": "拦截 assistant prefill",
            "kind": "boolean",
            "help": "针对指定模型进行本地处理。"
          },
          {
            "key": "intercept_assistant_prefill_models",
            "label": "prefill 拦截模型",
            "kind": "models",
            "help": "多个模型以逗号分隔。",
            "wide": true
          }
        ]
      },
      {
        "title": "缓存与请求结构",
        "description": "缓存断点和 TTL 独立配置，保留请求处理口径。",
        "fields": [
          {
            "key": "message_cache_control_rewrite",
            "label": "messages 缓存断点",
            "kind": "select",
            "help": "默认关闭额外改写，保留原生缓存布局。遇到缓存问题时可开启 sub2api 重新布置消息断点，保存后对后续请求生效。TTL 独立配置。",
            "options": [
              [
                "off",
                "关闭（保留原生布局）"
              ],
              [
                "sub2api",
                "sub2api 策略"
              ]
            ]
          },
          {
            "key": "cache_control_ttl_rewrite",
            "label": "cache_control.ttl",
            "kind": "select",
            "help": "关闭时保留客户端提交的 TTL。",
            "options": [
              [
                "off",
                "关闭"
              ],
              [
                "5m",
                "5 分钟"
              ],
              [
                "1h",
                "1 小时"
              ]
            ]
          },
          {
            "key": "message_body_order_fingerprint_enabled",
            "label": "请求体字段顺序指纹",
            "kind": "boolean",
            "help": "对齐 /v1/messages 顶层字段顺序。"
          },
          {
            "key": "message_top_field_filter_enabled",
            "label": "Messages 顶层字段清理",
            "kind": "boolean",
            "help": "按原规则清理固定根字段。"
          }
        ]
      },
      {
        "title": "Claude Code bootstrap",
        "description": "控制客户端收到的模型选项。",
        "fields": [
          {
            "key": "bootstrap_model_options_mode",
            "label": "模型选项模式",
            "kind": "select",
            "help": "配置模式使用下方模型数组。",
            "options": [
              [
                "passthrough",
                "透传上游"
              ],
              [
                "configured",
                "使用配置"
              ],
              [
                "hide_fable",
                "隐藏 Fable"
              ]
            ]
          },
          {
            "key": "bootstrap_additional_model_options",
            "label": "附加模型选项 JSON",
            "kind": "json",
            "help": "数组中每项必须包含合法的 model。",
            "wide": true
          }
        ]
      }
    ]
  },
  {
    "id": "access",
    "label": "客户端与画像",
    "icon": "shield",
    "description": "访问准入、版本画像与环境透传",
    "sections": [
      {
        "title": "版本画像与访问策略",
        "description": "请求画像选择与允许访问的客户端版本分别管理。",
        "fields": [
          {
            "key": "claude_code_profile_selection_mode",
            "label": "画像选择方式",
            "kind": "select",
            "help": "客户端模式按原始 UA 适配；账号模式使用目标画像范围。",
            "options": [
              [
                "client_version",
                "按客户端 UA 适配"
              ],
              [
                "account",
                "使用账号画像"
              ]
            ]
          },
          {
            "key": "claude_code_version_profile",
            "label": "默认版本画像",
            "kind": "select",
            "help": "保存默认画像将同步账号基础软件环境。",
            "options": [
              [
                "2.1.293",
                "2.1.293"
              ],
              [
                "2.1.280",
                "2.1.280"
              ],
              [
                "2.1.260",
                "2.1.260"
              ],
              [
                "2.1.257",
                "2.1.257"
              ],
              [
                "2.1.220",
                "2.1.220"
              ],
              [
                "2.1.197",
                "2.1.197"
              ],
              [
                "2.1.195",
                "2.1.195"
              ],
              [
                "2.1.187",
                "2.1.187"
              ],
              [
                "2.1.185",
                "2.1.185"
              ],
              [
                "2.1.173",
                "2.1.173"
              ]
            ]
          },
          {
            "key": "allowed_claude_code_versions",
            "label": "允许 Claude Code 版本",
            "kind": "text",
            "help": "支持精确版本、通配和范围，逗号或换行分隔。",
            "wide": true,
            "validation": "versions",
            "preset": "access"
          },
          {
            "key": "blocked_claude_code_versions",
            "label": "禁止 Claude Code 版本",
            "kind": "text",
            "help": "禁止规则优先于允许规则。",
            "wide": true,
            "validation": "versions"
          },
          {
            "key": "allowed_user_agents",
            "label": "其他允许 User-Agent",
            "kind": "textarea",
            "help": "支持可打印 ASCII 模式，逗号或换行分隔。",
            "wide": true,
            "validation": "agents",
            "preset": "agents"
          }
        ],
        "summary": "profile"
      },
      {
        "title": "上下文与环境透传",
        "description": "选择请求上下文处理方式，分别控制环境真值透传。",
        "fields": [
          {
            "key": "claude_code_context_sanitizer_mode",
            "label": "上下文风险控制",
            "kind": "select",
            "help": "报告模式只记录风险，不执行规范化。",
            "options": [
              [
                "off",
                "关闭"
              ],
              [
                "report_only",
                "仅报告"
              ],
              [
                "normalize",
                "规范化处理"
              ]
            ]
          },
          {
            "key": "passthrough_shell",
            "label": "透传 Shell",
            "kind": "boolean",
            "help": "保留客户端的 Shell 环境字段。"
          },
          {
            "key": "passthrough_os_version",
            "label": "透传 OS Version",
            "kind": "boolean",
            "help": "保留客户端的操作系统版本字段。"
          },
          {
            "key": "passthrough_working_dir",
            "label": "透传工作目录",
            "kind": "boolean",
            "help": "保留客户端的工作目录字段。"
          }
        ]
      }
    ]
  },
  {
    "id": "connections",
    "label": "连接与稳定性",
    "icon": "globe",
    "description": "代理复用、首次探测与流式连接",
    "sections": [
      {
        "title": "代理连接与首次 Hello 探测",
        "description": "连接池复用与会话首次探测分别控制。",
        "fields": [
          {
            "key": "proxy_client_pool_enabled",
            "label": "Rust 代理 HTTP 连接池",
            "kind": "boolean",
            "help": "复用 Rust HTTP 客户端连接。native 模型请求的连接复用由原生 SDK 管理。"
          },
          {
            "key": "session_hello_probe_enabled",
            "label": "首次 Hello 代理探测",
            "kind": "boolean",
            "help": "对有效上游 Session 进行首次探测。"
          },
          {
            "key": "session_hello_probe_strict",
            "label": "探测失败时阻断",
            "kind": "boolean",
            "help": "关闭严格模式时探测失败继续放行。",
            "enabledWhen": [
              "session_hello_probe_enabled",
              "true"
            ]
          },
          {
            "key": "session_hello_probe_timeout_secs",
            "label": "探测超时（秒）",
            "kind": "number",
            "help": "1–30 秒。",
            "min": 1,
            "max": 30,
            "enabledWhen": [
              "session_hello_probe_enabled",
              "true"
            ]
          },
          {
            "key": "session_hello_probe_success_ttl_secs",
            "label": "成功 TTL（秒）",
            "kind": "number",
            "help": "60–86400 秒。",
            "min": 60,
            "max": 86400,
            "enabledWhen": [
              "session_hello_probe_enabled",
              "true"
            ]
          },
          {
            "key": "session_hello_probe_failure_cooldown_secs",
            "label": "失败冷却（秒）",
            "kind": "number",
            "help": "10–3600 秒。",
            "min": 10,
            "max": 3600,
            "enabledWhen": [
              "session_hello_probe_enabled",
              "true"
            ]
          }
        ]
      },
      {
        "title": "流式稳定性",
        "description": "保持下游连接活跃，并限制上游持续静默。",
        "fields": [
          {
            "key": "stream_keepalive_enabled",
            "label": "启用流式 Keep-alive",
            "kind": "boolean",
            "help": "按配置间隔维持流式连接。"
          },
          {
            "key": "stream_keepalive_interval_secs",
            "label": "Keep-alive 间隔（秒）",
            "kind": "number",
            "help": "5–240 秒。",
            "min": 5,
            "max": 240
          },
          {
            "key": "stream_upstream_idle_timeout_secs",
            "label": "上游静默超时（秒）",
            "kind": "number",
            "help": "30–1800 秒。",
            "min": 30,
            "max": 1800
          }
        ]
      }
    ]
  },
  {
    "id": "warmup",
    "label": "预热与拦截",
    "icon": "spark",
    "description": "峰值预热与客户端探针处理",
    "sections": [
      {
        "title": "原生进程池",
        "description": "调整并发结束后的空闲保留时间。",
        "fields": [
          {
            "key": "native_idle_timeout_secs",
            "label": "额外空闲进程回收时间（秒）",
            "kind": "number",
            "help": "30–3600 秒，默认 120 秒。保存后由后台巡检同步，无需重启。账号整体保留一个基础暖进程，执行映像缓存继续保留。并发增加时按需补建进程。",
            "min": 30,
            "max": 3600
          }
        ]
      },
      {
        "title": "峰值预热",
        "description": "配置预热时间与模型，最近执行情况在预热记录中查看。",
        "fields": [
          {
            "key": "peak_prime_enabled",
            "label": "启用峰值预热",
            "kind": "boolean",
            "help": "按配置的小时触发预热。"
          },
          {
            "key": "peak_prime_hours",
            "label": "预热小时",
            "kind": "text",
            "help": "0–23 整数，逗号分隔；留空不指定小时。",
            "validation": "hours"
          },
          {
            "key": "peak_prime_model",
            "label": "预热模型",
            "kind": "text",
            "help": "使用现有模型标识。",
            "required": true,
            "wide": true
          }
        ]
      },
      {
        "title": "预热请求拦截",
        "description": "分别控制不同客户端预热和探测请求。",
        "fields": [
          {
            "key": "intercept_warmup_title_enabled",
            "label": "标题 / Warmup 拦截",
            "kind": "boolean",
            "help": "在本地处理对应预热请求。"
          },
          {
            "key": "intercept_warmup_suggestion_enabled",
            "label": "Suggestion Mode 拦截",
            "kind": "boolean",
            "help": "在本地处理建议模式请求。"
          },
          {
            "key": "intercept_warmup_haiku_probe_enabled",
            "label": "Haiku 探测拦截",
            "kind": "boolean",
            "help": "在本地处理对应 Haiku 探针。"
          },
          {
            "key": "intercept_auto_mode_classifier_stage1_mode",
            "label": "Auto Mode · Stage 1",
            "kind": "select",
            "help": "两阶段可分别配置。",
            "options": [
              [
                "passthrough",
                "放行上游"
              ],
              [
                "mock_allow",
                "本地允许"
              ],
              [
                "mock_block",
                "本地拒绝"
              ],
              [
                "error",
                "返回错误"
              ]
            ]
          },
          {
            "key": "intercept_auto_mode_classifier_stage2_mode",
            "label": "Auto Mode · Stage 2",
            "kind": "select",
            "help": "本地模式不请求上游分类器。",
            "options": [
              [
                "passthrough",
                "放行上游"
              ],
              [
                "mock_allow",
                "本地允许"
              ],
              [
                "mock_block",
                "本地拒绝"
              ],
              [
                "error",
                "返回错误"
              ]
            ]
          }
        ]
      },
      {
        "title": "后台状态分类",
        "description": "按完整模型 ID 匹配 Claude Code 后台分类请求。",
        "fields": [
          {
            "key": "intercept_cli_bg_status_classifier_mode",
            "label": "后台分类处理",
            "kind": "select",
            "help": "本地模拟时不访问上游。",
            "options": [
              [
                "passthrough",
                "放行上游"
              ],
              [
                "mock",
                "本地模拟"
              ]
            ]
          },
          {
            "key": "intercept_cli_bg_status_classifier_models",
            "label": "适用模型",
            "kind": "models",
            "help": "留空表示不在本地模拟任何模型。",
            "wide": true
          },
          {
            "key": "intercept_cli_bg_status_classifier_identity_injection_enabled",
            "label": "缺失时注入 Claude Code 身份块",
            "kind": "boolean",
            "help": "本地模拟时暂不生效，切回放行后恢复已保存的值。",
            "disabledWhen": [
              "intercept_cli_bg_status_classifier_mode",
              "mock"
            ]
          }
        ]
      }
    ]
  },
  {
    "id": "observability",
    "label": "日志与观测",
    "icon": "task",
    "description": "诊断日志与非流请求观测",
    "sections": [
      {
        "title": "请求诊断",
        "description": "日志模式仅对后续请求生效。",
        "fields": [
          {
            "key": "request_diagnostics_log_mode",
            "label": "后续请求日志",
            "kind": "select",
            "help": "debug 配合账号内容采集开关保存脱敏内容。",
            "options": [
              [
                "info",
                "info · 摘要"
              ],
              [
                "debug",
                "debug · 脱敏内容"
              ]
            ]
          },
          {
            "key": "request_diagnostics_rejected_body",
            "label": "本地拒绝入站正文",
            "kind": "select",
            "help": "仅在 Debug 下生效。完整正文仍会脱敏，并保留原有保留期。",
            "options": [
              ["preview", "限长预览"],
              ["full", "完整正文 · 脱敏"]
            ]
          }
        ]
      },
      {
        "title": "429 与非流请求",
        "description": "按需启用观测和探针缓存。",
        "fields": [
          {
            "key": "log_429_request_enabled",
            "label": "记录 429 请求",
            "kind": "boolean",
            "help": "按原观测规则保存请求信息。"
          },
          {
            "key": "log_non_stream_request_enabled",
            "label": "记录非流请求",
            "kind": "boolean",
            "help": "开启非流请求观测。"
          },
          {
            "key": "non_stream_probe_cache_enabled",
            "label": "非流单消息探针缓存",
            "kind": "boolean",
            "help": "复用符合条件的探针结果。"
          },
          {
            "key": "log_429_request_body_limit",
            "label": "请求体字符上限",
            "kind": "number",
            "help": "0–1048576 字符。",
            "min": 0,
            "max": 1048576
          }
        ]
      }
    ]
  },
  {
    "id": "history",
    "label": "预热记录",
    "icon": "clock",
    "description": "查看最近预热的结果与耗时",
    "sections": []
  }
];
