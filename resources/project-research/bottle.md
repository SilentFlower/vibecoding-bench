# 真实项目审查：Bottle

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[bottlepy/bottle](https://github.com/bottlepy/bottle)。
- 固定提交：[8ec5fe29420d14998c0d86885083983eaea8b839](https://github.com/bottlepy/bottle/tree/8ec5fe29420d14998c0d86885083983eaea8b839)，版本 0.14-dev。
- 许可证：MIT。保留LICENSE中Marcel Hellkamp归属及许可。
- 单文件WSGI Web框架，原生路由、request/response、模板、插件、上传和静态文件；核心标准库即可运行，无独立数据库或账号依赖。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 220／2917290 |
| 产品 Python 模块／行数 | 1／4566（bottle.py） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 4.18 秒，venv 52044541 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 382 通过、0 失败、0 错误、0 跳过、0 预期失败；另 0 个原生子测试通过；墙钟 1.08 秒 |
| 子进程峰值 RSS | 57728 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

核心零依赖、Python≥3.9；本轮pytest、Mako、Jinja2及其MarkupSafe依赖精确冻结。添加模板依赖后重新跑382项全过。没有启动run()服务端、连接数据库、安装历史外部server adapters或运行多平台。

最终382通过，无普通skip／xfail。此前不含可选模板的日志保存为core-without-template-dependencies-*。上游server适配器有标untested的分支，本轮不声称这些通过。

Bottle.route创建Route，经Router.match选中后由_handle绑定线程本地request/response、触发hook、调用插件包裹的callback；_cast把结果转WSGI字节迭代器，wsgi调用start_response。BaseRequest解析query/body/multipart，FileUpload处理实际文件，Template各引擎有独立适配器。已读真实定义及挂载、合并、JSON、文件上传和模板搜索。

## 原生使用场景和改进研究

原生直接WSGI调用/hello/<name>返回200 JSON，捕获实际头／字节，无网络监听。复现子Bottle错误由父404 handler处理（parent-error）；FileUpload.save(Path)误按file-like调用导致AttributeError；charset直接赋值无setter。上传100000/103000/300000字节全部成功，因此旧#1470不当作现版BUG；after_request对abort错误设置的X-Review头已保留，旧#1125排除。已读模板固定extensions及lookup遍历、merge无prefix、urlparts直接采用forwarded头等源码；以下多数是显式增强，不误报成既有承诺。

完整 [20 步路线](./bottle-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/bottle/`；固定源码当前位置 `/tmp/github-research-bottle-2rfyut7m/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/bottlepy/bottle.git <checkout>
git -C <checkout> checkout --detach 8ec5fe29420d14998c0d86885083983eaea8b839
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

WSGI全套与合成请求在独立临时检出／HOME／venv实跑，未跑账号镜像、外部server矩阵或真实网络下载。close回调最多证明WSGI迭代结束／关闭，不等于客户端完整接收。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
