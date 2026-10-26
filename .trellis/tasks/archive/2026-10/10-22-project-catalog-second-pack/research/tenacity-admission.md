# Tenacity 第二批内容包准入记录

## 范围与状态

本仓正式内容为 `project_library/projects/tenacity/`，环境为 `environments/tenacity-py312/`：**5 场景／13 个唯一任务**，understand 2、consult 3、diagnose 4、plan 2、modify 2，11 项非修改。全部任务 `requires=[]`，默认诊断→修改只是业务顺序；两项修改在各自场景原版上独立验收，不累计代码。

逐仓真实原生准入通过。整包评审协议、模拟调度与材料消费、页面／API／SQLite、预算／用量、Git／Docker 字节交付及正式 Check-All 仍由主会话执行。本仓通过不等于整批已完成，不代表真实模型回答质量或生产上线。真实模型／OAuth 调用均为零，未提交、推送或部署。

## 固定真实源码与离线环境

上游为 [jd/tenacity@32ac68f0941319c0d2f4fb927f96e4ee29bb46c6](https://github.com/jd/tenacity/tree/32ac68f0941319c0d2f4fb927f96e4ee29bb46c6)，**97 个真实 Git blob**，Apache-2.0。完整 LICENSE 原字节 SHA256 为 `58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd`；版权头保留。构建版本采用上游 hatch-vcs，不把浅检出的动态开发版本当正式发行号。

主会话已依据固定官方 Git 对象导出源码和模式清单。本仓最终重核 `seed/library/` 的文件全集与每个 SHA256：97 项完全相同，缺失／多余／不同均为零，两个目标没有预修。上游 `README.rst` 是 mode120000 的链接 blob；为满足内容禁止链接的契约，按其原目标文本字节存为普通文件，清单保留原 Git mode／blob，不创建实际 symlink，也不伪称上游原来就是普通文件。完整来源清单随 `tenacity-admission.json` 保存，原始入口为证据根 `source-files.json`。

目标 account 镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1`，实际 RepoDigest 为 `sha256:943ecef29346447036ec35e2156cc1e4a2f32153e483311531794057a8e18216`，linux-amd64、Python **3.12.15**。业务和回归均在 UID1000、无网络、只读源码／根目录、无账号 HOME／凭据的临时验证容器执行；真实业务只用合成文件。

12 个真实锁版 wheel 及逐 SHA／大小位于环境 profile：attrs26.1.0、idna3.20、iniconfig2.3.1、outcome1.3.0.post0、packaging26.3、pluggy1.7.0、Pygments2.21.0、pytest9.1.1、sniffio1.3.1、sortedcontainers2.4.0、tornado6.5.10、trio0.34.0。没有安装发行版 Tenacity 替代候选；没有猜装 pytest-asyncio 或额外 pytest-subtests。pytest9 内置子测试行为按当前真实报告冻结。

业务资源 **30 秒／256 MiB／PID64**，回归单独 **90 秒／512 MiB／PID64**，均实际通过。原版校准离线准备 5.275 秒、总 8.928 秒，校准子进程累计观测峰值 RSS 72,756 KiB；该口径不等于整个容器、模型 CLI 或账号所有角色的总资源。准备阶段与实际业务时限分开。

## 场景、材料与入口

| 场景 | 稳定任务 | 业务边界 |
| --- | --- | --- |
| TN-S01 等配置文件就绪再继续启动 | U01、C01、P01 | 真实有限文件读取、策略生命周期、只重试暂态缺文件与启动副作用规划 |
| TN-S02 重试排查与运行观测 | D01、C02、U02、D02 | 先取证、最终异常政策、after钩子与重入统计诊断 |
| TN-S03 等待预算与异步取消 | C03、P02 | stop边界、真实await／取消、调用方总超时方案 |
| TN-S04 零倍率为什么跳到等待上限 | D03、M01 | 独立诊断并修复零指数贡献的无意义溢出 |
| TN-S05 大型组合等待策略 | D04、M02 | 独立诊断并修复内置深树求值，保护分组与自定义策略 |

首问、业务材料说明、分支条件及 rubric 英文；页面 title／category／description／goal 中文。源码、原始 traceback 和“华东”等合成业务值原样保留。11 个非修改任务授权路径为空，不产生代码接受检查点。

全部入口：S01 normal；S02 normal、diagnose_only（只选 D01）、unavailable（只选 D01 并给出证据已丢失说明）；S03 normal；S04／S05 各 normal、diagnose_only、modify_direct。两个修改首问均自足，直接入口具有相同完整公开复现和精确授权。

D01 初始仅版本与一次失败症状；`loader-evidence` 在实际请求完整异常／重试配置且没有 unavailable 记录时，才披露完整 loader、精确合成输入／事件及 **当前镜像真实执行得到的 1,882 字节 traceback**。通用 rubric 不提前包含隐藏异常或确定策略；该题不挂初始 native，避免将私有复现事实提前反馈。材料不可提供时，`insufficient_information` 是可正常结案的结果。

## 当前完整上游回归

主会话已完成当前镜像原版可信校准，本责任人未重复该昂贵通过项。最终可信 runner SHA256 为 `b3e75e056b684fa6d5a6a4871bf8793b8422d373460562110207612c97ba65c3`，与共享工具逐字节相同；冻结合同 SHA256 为 `e65bc78e63d5e4e5047af48d23e5a89dacd01f1bf89599654e4dff84fd773089`。

原版及两个独立参考均为 **185 个主 collection 节点 passed，15 个真实子测试 passed，0 failed／error／skip／xfail**。JUnit 恰有 **185 个 testcase 元素**；suite 的 200 汇总口径包含子测试，不能再计成200个主节点或将185＋200相加。子测试逐父节点、出现 ordinal、when、真实 context 与 outcome 和原版完全一致，重复空 context 没有错误去重，`subtests_match_contract=true`；主节点集合也严格匹配。

参考 M01 完整 runner 3.090 秒、M02 4.194 秒，均在独立回归资源下实际执行。完整证据保留同步、asyncio、trio、Tornado 与原生 unittest子测试，不靠删测试、缺依赖skip或只跑目标切片放行。旧六仓私有 runner／合同未改。

## 独立业务与负对照

共 **17 个产品真实验证入口案例**全部符合预期：10 个只读任务的原生事实、两个原版目标预期失败、两个独立参考业务＋完整回归、三个错误修复预期拒绝。语义评分与原生事实分开：咨询／方案的现有API见证不冒充候选已实现新业务，也不证明真实模型答复质量。

- 文件场景真实读取合成 JSON：前两次缺失、第三次 before 发布文件；独立调用计数3、两次sleep参数0.2、精确返回对象。初始已有文件一次成功，坏 JSON 一次失败且无sleep，永久缺失三次后按政策结束。完整逐事件顺序保护 before／retry／after／wait／stop／before_sleep／sleep；并核初始化标志只有读取与字段验证成功后才写一次。
- 最终异常政策分别观察 RetryError及 last_attempt、原 FileNotFoundError、显式fallback对象；不可重试异常与首成功均不触发耗尽callback。重入真实结果为内层3次／外层2次，外层第二次真实状态编号2而共享统计4；正常非重入对照仍正常，不把统计串扰等同实际重试4次。
- 真实 RetryCallState 在 elapsed2／upcoming4、3、2 下核 stop_before_delay 与 stop_after_delay，不修改平台时钟。真实 AsyncRetrying 读取第三次合成文件、sleep为真正await并让出事件循环；取消等待中的任务真实传播 CancelledError且无下一次尝试，永久缺失有限结束。
- M01 覆盖0／0.0、整数／浮点底数、attempt1／1024／1025／2049、min与clamp排序、随机指数上下界、jitter0／确定采样／小max、每次恰一次draw、既有正倍率增长与提前封顶。真实控制器两次失败后成功，sleep spy记录零等待；没有真实长睡眠。原版两个float参与的溢出路径失败，而整数0＋整数2仍是正常对照。错误“零倍率直接return0”被下界／随机区间断言拒绝。
- M02 验证1000／2000级左／右／混合树、每层Python builtin `float(sum(...))`、空组合、浅树非有限数、位置参数及falsy callable、不透明自定义子类、逐叶调用顺序、shared DAG每出现次求值、未进入节点属性变更／已进入tuple迭代、叶异常阻止后叶、自环／互环明确ValueError以及全局recursionlimit不变。错误“用isinstance遍历子类”与“将各层值压平成全局sum”分别被自定义行为及浮点分组反例拒绝。
- 新增公开回归另在无网容器执行：M01一项、M02两项在原版均失败、相应独立参考均通过。产品完整回归仍从固定baseline恢复原测试；候选新增测试不替代冻结oracle。

全部sleep spy、random替换和业务outcome时间设置仅在一次验证子进程内，平台driver、timeout及累计预算保持真实。私有参考及错误候选均不进入正式seed。

## 证据、命令与交接

证据根 `.deploy/project-catalog-second-pack/tenacity/`：

- `source-files.json`、`requirements.txt`、`calibrate.py`、`calibration-001/`：主会话已完成的固定来源、当前镜像原版校准、合同、逐报告、XML、资源及清理，原样保留。
- `build_content.py`、`make_references.py`：内容与两份独立原版参考生成；`references/TN-M01/`、`references/TN-M02/` 为控制端私有候选，`wrong/` 是负对照。
- `validation-library/`：可直接传既有 `scripts/validate-project-scenarios.py` 的单仓目录；`validation/commands.jsonl` 保留全部实际精确命令，逐项 JSON／log 包含候选摘要、真实结果与完整回归分母。
- `public-tests-v1/`：新增测试原版失败／参考通过的四次执行、stdout／stderr及XML。
- `disclosure-proof.json`：真实执行公开披露程序后产生完整JSONDecodeError traceback的证明；`disclosure-cleanup.json` 记录该专用容器移除。
- `mock-answers.json`：13个任务键及 `TN-D01-question`、`TN-D01-unavailable` 两接续答复；`mock-response-manifest.json` 给两参考路径和分支映射，已通知 fixtures准备者。
- `cleanup.json`：本仓专用命名容器剩余零；产品验证器按正常生命周期清理其临时容器。未删除他仓、旧证据、未知容器或生产数据。

示例入口（实际参数与输出以commands.jsonl为准）：

```bash
.deploy/project-iteration-repairs/venv/bin/python scripts/validate-project-scenarios.py --root .deploy/project-catalog-second-pack/tenacity/validation-library --project tenacity --task TN-M02 --candidate .deploy/project-catalog-second-pack/tenacity/references/TN-M02 --image ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1 --with-regression
```

原版和负对照失败均为预期结果，没有隐藏或覆盖失败。整个四仓交付仍以主会话后续整包机制、页面及交付证据为准。
