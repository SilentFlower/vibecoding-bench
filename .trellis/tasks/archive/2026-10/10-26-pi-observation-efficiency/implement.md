# 观察效率实施计划

## 前置条件

- 父任务联合 Brief 与本子任务相同范围已获批准后激活此子任务；联合 Brief 与事件唤醒增量决定已经获得当前对话中的用户确认。
- 按 trellis-route 与 trellis-before-dev 加载上下文；inline 执行，不派发代理。

## 实施步骤

- [x] 读取完整 ProjectsService._observe、工具 DTO、PiTerminal.observe 和现有夹具定义，先增加有价值的噪声等待/事件唤醒/取消回归。
- [x] 核实固定 CLI 钩子，在本次执行 settings 中保留既有钩子并增加只写本地提示的通知，验证会话/来源隔离和退出清理。
- [x] 实现原生交互事件、已确认显示噪声归一化及约一秒稳定新画面唤醒，检测程序不代替 Pi 决策。
- [x] 实现默认等待与纯画面合并，保留首次/输入后即时观察、显式零等待、终端失效/退出/额度和本轮预算。
- [x] 增加模型视图及 full_screen 参数；实现可还原行片段、相同画面省略、较大差异全屏回退。
- [x] 在 fresh/摘要成功/重启边界重建模型基线，补混合工具与取消顺序验证。
- [x] 检查页面完整快照、双空间、菜单、多行输入、旧 observation_id 和未知投递保护。
- [x] 保存固定时间轨迹的观察返回对比、合成文本的字节前后对比、mock 上游请求计数及证据边界。
- [x] 更新共同观察契约；定向验证证据保存后返回父任务，统一进入联合 Check-All。

## 适用验证

```bash
PYTHONPATH=orchestrator python3 -m unittest test_projects_agent test_projects_terminal test_projects_feed test_projects_store test_projects_single_objective test_projects_schedule_edges test_projects_pi_round
node --test images/pi-agent/host.test.mjs
```

新增观察策略回归可放入独立 `orchestrator/test_projects_observation.py`，名称为拟新增而非既有接口。必要时单独运行其真实回放，记录实测，不把 355→几十次目标当成预先通过。

## 回退与限制

回退本次 Python 等待与 Node 投影即可恢复既有模型视图，数据库无需迁移。原始观察继续可读；未通过完整回归前不扩大等待上限、不改动调度和生产任务。若实际模块拆分会影响镜像文件列表，必须在交付前核对现有 Dockerfile 与构建上下文。

## 联合交付证据

本子任务在父任务完成统一 full Check-All，定向与集成证据见 `../10-26-pi-efficiency-feedback/research/validation.md`。规范已同步；Git 交付与 completed/Close 尚待联合提交计划确认。
