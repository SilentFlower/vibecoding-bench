# Flask：真实 GitHub 项目研究

研究完成；已固定来源、许可和源码，实际跑通适用完整原生基线及普通业务场景，逐条形成 [20 个独立交付与验收边界](./flask-roadmap-20.md)。**本轮仅研究，未实施路线，未冻结独立验收或接入正式内容库。**

## 来源、许可与真实工程

官方来源为 [pallets/flask](https://github.com/pallets/flask)，固定完整提交 [`d086db856be187255b8ec61ef409357393020f32`](https://github.com/pallets/flask/tree/d086db856be187255b8ec61ef409357393020f32)，该提交版本为 `3.2.0.dev`，提交时间为 2026-10-07。`repository.json`、`commit.json`、实际 detached checkout 与 `revision.txt` 对应。已读 `LICENSE.txt`：BSD-3-Clause，保留 Pallets 版权声明、三项再分发条件与免责声明；不以贡献者姓名背书。

真实工程跟踪 **236 文件、1,785,020 字节**；83 个 Python 文件合计 **18,333 行**，包括测试与工具。保留 src/flask 原结构，未改写为同构 app.py。主要读取 Config 各加载器、DefaultJSONProvider、App.add_url_rule、routes_command、DispatchingJinjaLoader、模板同步/流式渲染、FlaskClient、flash 消费、资源读取、公开导出与相关原生测试；字段与签名按该提交核对。

## 原生基线与轻量成本

独立源码、venv 和 HOME：`.deploy/github-100-research/resume-app/flask/{source,venv,isolated-home}`。Python **3.12.3**，Linux x86_64。实际安装本地 editable 工程及上游测试组 `pytest/asgiref/python-dotenv`，安装 **9.907 秒**；环境 **54,466,080 字节**。完整依赖版本见 `requirements-frozen.txt`，其中 Werkzeug 3.1.9、Jinja2 3.1.6、Click 8.5.0、itsdangerous 2.2.0、Blinker 1.9.0、asgiref 3.12.1；这不是省略可选 async 后的简化测试。

完整原生默认测试 **494 通过、0 失败、0 错误、0 跳过**，耗时 **2.531 秒**，实测测试进程峰值 RSS **58,612 KiB**。命令含 `-p no:cacheprovider` 以避免测试缓存改变检出，不修改测试筛选。未跑 Python/OS 矩阵、文档构建、风格与静态类型检查；不把这些声称已验证。无数据库、云凭据或外部账号要求。业务观察用原生 test_client，不监听端口；未访问外部业务系统。

## 原版业务场景与二十项研究依据

`observe.py` 从当前固定检出加载原生 Flask，`observations-result.json.module` 明确指向本轮 `resume-app/flask/source/src/flask/__init__.py`。Unicode 商品动态路由、两次 Cookie 会话计数、既有 async 路由均实际成功；20 个观察键逐项记录原版现状、替代方式与入口缺口。

最明确的原版反例是重复 endpoint 注册：抛 AssertionError 后 `/new` 仍进入 url_map，并返回旧视图，作为第 20 步原子性修复依据。环境父键为数字且又加载子键时，TypeError 前已有部分参数写入，作为可选事务加载的增强依据。筛选 success 闪存消息会把未展示 warning 一并从下一请求消费掉，这是已存在的约定，路线只提议新增选择性消费。JSON 日期采用 HTTP 日期并丢失微秒也按兼容增强处理。async 模板反例附带原生未等待协程警告，保留在 `observations.log`，不掩饰为已修复。

路线中 routes JSON、路由只读审查、配置约束/事务/来源/覆盖/嵌套导出、JSON 严格配置/类型注册/日期格式/NDJSON、模板来源/async/蓝图命名空间/测试捕获、消息按类别消费、客户端默认请求配置、包资源后端、文本 IO 控制均各有明确交付。已有自定义 JSONProvider、EXPLAIN_TEMPLATE_LOADING、template_rendered 信号、environ_base、Response 生成器、from_prefixed_env 的 JSON 与嵌套加载、encoding 参数等均明确列为现有能力和替代方案，未重复包装成新增。19 项为研究者增强提案，不声称上游承诺接受。

## 证据与重跑

证据根：`.deploy/github-100-research/resume-app/flask/`。`baseline-result.json`、`baseline-tests.log/xml/time` 保存完整测试结果；`installation-result.json`、`installation.json` 与冻结依赖记录安装；`size.json` 记录规模；`observe.py`、`observations-result.json`、`observations.log` 保存原版业务反例；`review-result.json` 及 `evidence-sha256.json` 为复核入口。旧 `cli-config` 证据保留但本报告不依赖旧临时路径。

在项目根可直接重跑已准备环境：

```bash
HOME="$PWD/.deploy/github-100-research/resume-app/flask/isolated-home" .deploy/github-100-research/resume-app/flask/venv/bin/python .deploy/github-100-research/resume-app/flask/observe.py
```

完整基线在 source 目录运行独立 venv 的 `python -m pytest -q -ra -p no:cacheprovider --junitxml=<证据目录>/baseline-tests.xml`，同时设置上述隔离 HOME。异机先 clone 官方 URL 并 `git checkout --detach d086db856be187255b8ec61ef409357393020f32`，独立 venv 按 `requirements-frozen.txt` 恢复依赖，将 editable 项替换为本地固定检出，确认导入路径后再测。原始证据与 venv 是本机资源，并非跨机器可用性保证；首次安装需要依赖源，冻结验收前还需准备离线 wheelhouse。

未来冻结验收应真实调用候选源码并校验响应/会话/配置/模板与文件副作用，累计回归此前步骤。本轮未修改上游检出、正式库或产品代码，未提交、推送、部署或向上游发消息。
