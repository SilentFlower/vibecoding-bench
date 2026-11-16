# 本轮验证证据

## 实现与体验

- 工作区先显示框架，账号与草稿独立读取；项目池、模型、历史独立加载并提供区域重试。会话只合并在途请求，后续入口重新交换。
- 环境列表每轮最多三个工作者，按原顺序返回；每个工作者复制请求上下文，保留维护锁与只读投影。
- 主导航固定亮色、按内容宽度排列；目标状态归入侧栏卡片，当前交付与历史入口共用读取逻辑。交付弹窗从历史分区移到共享层，避免被分区隐藏。
- 交付窗口接近全屏，桌面文件导航与阅读分栏，手机上下分区；源码与验收报告各自滚动。更新说明、平台、维护与版本记录独立分区。

## 合成延迟样本

真实生产构建配合完全拦截的合成接口，阻塞目标请求1500ms。优化前与优化后均为本地浏览器样本，线上实际耗时需上线后测量。

| 场景 | 优化前 | 优化后 |
| --- | --- | --- |
| 慢登录草稿 | 任务页2108ms可见 | 正式账号348ms可见，草稿独立等待 |
| 慢会话 | 任务页约1971ms可见 | 框架334ms可见，会话期间动作受控 |
| 慢环境列表 | 环境页1906ms可见 | 框架264ms可见，列表独立等待 |
| 慢字体/历史/模型/项目池 | 阻塞任务首屏或初始化 | 屏障释放前框架及已完成区域可用 |

复现入口：`deploy/flower2api/verify_workspace_experience.py`。最近机器结果及截图位于`.deploy/console-workspace-experience/`；该目录为本地证据。

## 已通过验证

- `npm --prefix apps/web run build`：TypeScript与Vite构建通过。
- `node --check apps/legacy-web/{app,projects,environments}.js`：三个文件分别通过。
- `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_account_runtime test_environment_summary`：113项通过，含并发上限、排序、上下文、维护锁与空列表/异常。
- 浏览器入口：`verify_workspace_experience.py`、`verify_native_environments.py`、`verify_environment_cpu_summary.py`、`verify_runtime_workspace_design.py`、`verify_project_workspace_design.py`、`verify_task_account_config.py`、`verify_task_feedback.py`、`verify_workspace_stability.py`、`verify_management_ui.py`、`verify_system_update_browser.py`、`verify_dashboard_update.py`、`verify_dialog_typography.py`、`verify_update_design.py`均通过。
- 视口1440×900、1280×720、390×844：阅读区、导航、目标状态、原型一致性、长文本、Esc及焦点恢复；旧dark偏好与系统深色下固定亮色，独立兼容入口通过。
- 系统更新取消零安装写入、冻结revision/UUID/SHA、双击幂等、断线恢复、快照/迁移、回退与恢复通过。旧脚本使用独立版本历史入口、组件选择菜单和专属确认dialog定位；自动检查请求与业务写入分别核对。

## 收尾状态

后端完整unittest运行1310项：原有1308项通过、1项报错、1项跳过。唯一报错为抓包测试依赖旧注释定位；已改为startClock函数边界，test_tls_capture_artifacts的8项定向复验全部通过。原型导航padding/margin已同步，audit_token_task_design.py全部采样无差异。Check-All复用原完整检查证据并对两项修复轻量重检，通过；CHK-001、CHK-002均已解决。

规范已同步4个权威文件，diff与本地链接校验通过。精确Git计划将业务变更与本任务记录分为两次提交，既有397个无关dirty路径保留。
