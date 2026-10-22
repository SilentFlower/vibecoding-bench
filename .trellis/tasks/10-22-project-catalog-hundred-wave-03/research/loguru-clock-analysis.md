## Bug Analysis: 原生轮转测试遇宿主墙钟回拨

### 1. Root Cause Category

- **Category**：E，隐含环境假设。
- **Specific Cause**：上游测试用真实sleep等待以墙钟定义的轮转边界，隐含等待期间墙钟稳定前进。只读profile记录一次2.500141653秒单调等待仅经历1.65800888秒墙钟，差约-0.842秒；独立宿主CLOCK_REALTIME采样再次捕获约-0.836秒及-0.830秒回拨。因此不能将这些失败归为已证实的Loguru缺陷。

### 2. Why Fixes Failed (if applicable)

1. 第一轮100进程屏障在pids64不足；读实际用例后只为回归入口设置128，业务仍64。无证据支持的僵尸/init猜测被否定，未引入reaper。
2. 完整轮转文件及后续完整重跑仍分别失败于不同真实时间用例；单例顺序通过不能证明整套通过。
3. 增加只读time.time_ns、CLOCK_REALTIME及monotonic观测后识别回拨；没有改系统时钟、冻结时间、修改库、删测试或放宽断言。
4. 第六次完整原始集合实际1679通过、46上游跳过，1725主项封存。此前失败、诊断和资源原件全部保留。一次成功不表示宿主时钟问题已经修复。

### 3. Prevention Mechanisms

| Priority | Mechanism | Specific Action | Status |
| --- | --- | --- | --- |
| P0 | 环境证据 | 同时核墙钟与单调时钟，保留原始测试及独立采样 | DONE |
| P0 | 完整回归 | 只用未修改的完整成功结果封存合同，失败不得冒充skip | DONE |
| P1 | 诊断边界 | 报告宿主时钟仍不稳定；后续真实时间失败先核回拨，禁止伪造稳定时钟成绩 | DONE |

### 4. Systematic Expansion

- **Similar Issues**：依赖真实sleep与文件mtime的其他本地原生测试。
- **Design Improvement**：区分产品业务事实与测试环境时间来源；本轮不修改平台时钟、系统权限或上游测试。
- **Process Improvement**：未知时钟失败先获取能区分假设的观测，避免不断修改无关进程控制。

### 5. Knowledge Capture

- [x] 本记录、loguru-host-clock-observation.json与additional-native/attempt-004保存可复核证据。
- [ ] 阶段规范同步时评估是否补充可复用的真实时间环境合同，由Update-Spec统一处理。
