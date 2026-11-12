# 真实项目审查：ConfigObj

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[DiffSK/configobj](https://github.com/DiffSK/configobj)。
- 固定提交：[b7707c94c0317b8f89b704a01525a68eb6c72521](https://github.com/DiffSK/configobj/tree/b7707c94c0317b8f89b704a01525a68eb6c72521)，版本 5.0.9。
- 许可证：BSD-3-Clause（实际 LICENSE 原文与 setup.py 一致；GitHub 元数据仅标 Other）。已直接读取原生 LICENSE，保留 Foord／Larosa／Courtwright／Dennis 版权、三项条款和免责声明。jazzband/configobj 为 404，不作为来源。
- 注释和顺序保留的 INI 配置解析、嵌套节、往返写入、插值和 configspec 类型验证，纯 Python，无外部服务或凭据。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 33／380361 |
| 产品 Python 模块／行数 | 3／3936（src/configobj/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 8.25 秒，venv 50136082 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 79 通过、0 失败、0 错误、0 跳过、0 预期失败；墙钟 0.98 秒 |
| 子进程峰值 RSS | 75236 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

核心无必需第三方依赖，validate 随源码发布；Python ≥ 3.8。本轮仅装本地源码和 pytest，构建使用 setuptools。没有运行 Python 多版本矩阵、文档构建或覆盖率 HTML 生成。

pytest 79 项全过，无跳过；CI 两个额外 doctest 入口也通过，原生配置脚本分别统计两批 doctest、验证脚本 198 个例子，详见 additional-baseline-result.json 和 *-doctests.log，未将例子与 pytest 项数混加。

ConfigObj 继承 Section，维护 scalars／sections／comments／inline_comments 等真实字段。_load 解码并 _parse，Section.__getitem__ 按选择的 InterpolationEngine 惰性展开；write 暂停插值、按声明顺序输出并恢复。validate 根据 configspec 经 Validator.check 转换值；flatten_errors 和 get_extra_values 已存在。已读构造器、引号和写入逻辑、merge、拷贝状态、插值递归、验证与 reload；内建 recursive merge、restore_default、模板插值、默认值复制均不重复算增强。

## 原生使用场景和改进研究

原生场景实际写 UTF-8 嵌套 server 配置，重新读取后通过 integer(min,max) 验证得到 port=5432 与中文名称。原版观察确认：list_values=False 的 hash 字符和 _inspec 的首空白／空值往返失真、混合三引号值截断；含等号键丢引号后 ParseError；deepcopy 将原始插值表达式固化为 bar.txt；merge 丢新增子节注释；验证先把 a 转 int 后 $a 插值抛 TypeError。公开缺口通过签名与拒绝未知参数确认，已有异常和策略作为兼容边界保留。没有运行开放 #281 的大规模 ReDoS 输入，该项不作为本轮已复现缺陷。

完整 [20 步路线](./configobj-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/configobj/`；固定源码当前位置 `/tmp/github-research-configobj-hkf7efnn/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/DiffSK/configobj.git <checkout>
git -C <checkout> checkout --detach b7707c94c0317b8f89b704a01525a68eb6c72521
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。额外执行 `<venv>/bin/python src/tests/configobj_doctests.py -v` 和 `<venv>/bin/python -m configobj.validate -v`；它们为官方 CI 原生命令。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

临时检出、独立 HOME／venv 实测，未跑正式账号镜像、类型检查或系统故障注入；原子写提案不等于断电持久性保证。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
