# 真实项目审查：TOMLKit

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[python-poetry/tomlkit](https://github.com/python-poetry/tomlkit)。
- 固定提交：[eddd27e43a62fe58707c311bfad2f52e72493f53](https://github.com/python-poetry/tomlkit/tree/eddd27e43a62fe58707c311bfad2f52e72493f53)，版本 0.15.2。
- 许可证：MIT。保留 LICENSE 的 2018 Sébastien Eustace 版权和许可；测试子模块 BurntSushi/toml-test 另保留其自身许可。
- 保留注释、空白、引号和顺序的 TOML 文档读写／修改库，适于 pyproject 等真实配置编辑，无必需服务。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 83／834217 |
| 产品 Python 模块／行数 | 12／6359（tomlkit/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 3.15 秒，venv 45946506 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 1203 通过、0 失败、0 错误、0 跳过、0 预期失败；墙钟 2.48 秒 |
| 子进程峰值 RSS | 55020 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

核心无必需第三方运行依赖、Python ≥ 3.9；本轮依上游开发约束装 pytest~=7.2、PyYAML~=6.0、pytest-cov~=4.0。构建用 poetry-core。首次默认 clone 未取测试子模块导致 collection 错误，已保留 before-submodule-*，随后按固定 gitlink 08ed8697864548b3cdb4b8decbf496bef47e1c82 获取 BurntSushi/toml-test 并重跑 1203 项全过。主仓文件数不包含该外部语料的展开文件数。

最终完整适用集合无失败、无跳过；没有把缺少子模块的准备错误叫作产品 BUG。未执行 Sphinx、mypy、ruff、多Python版本或外部 fuzz 持续运行。

api.parse→Parser 构建 TOMLDocument／Container／Item；Table、InlineTable、Array、AoT 保存值和 Trivia 并由 as_string 序列化。OutOfOrderTableProxy 拼接不连续表片段。TOMLFile.read 记录 LF／CRLF／mixed，write 按现有换行规则输出。已读相关定义、Container 的 append／replace／delete 以及 Item 编码路径；已有自定义编码器注册、原生数组 insert/add_line、表 indent、混合换行保持均不重计。

## 原生使用场景和改进研究

原生场景读取带中文注释和 inline 注释的 server.port 文件，将5432改为6432，写回后用标准库 tomllib 校验且两类注释均保留。observe.py 对照标准库实际复现：点分 inline 子键删空产生重复逗号；深层缩进／后置表片段／AoT unwrap 三类代理失败；Array *=2 值和序列化不同步；子表脱离父路径和 scalar→table 捕获兄弟键；删空虚拟嵌套表不再序列化；sort_keys 仅整理顶层。前述相关代理问题合为一步，结构重写两个路径问题合为一步，不用失败矩阵凑数。普通赋值将单引号改双引号已观察，为显式保样式增强。

完整 [20 步路线](./tomlkit-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/tomlkit/`；固定源码当前位置 `/tmp/github-research-tomlkit-4z5_8onf/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/python-poetry/tomlkit.git <checkout>
git -C <checkout> checkout --detach eddd27e43a62fe58707c311bfad2f52e72493f53
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。clone 后额外 `git submodule update --init --depth 1`，核对 tests/toml-test 固定提交 08ed8697864548b3cdb4b8decbf496bef47e1c82。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

只在隔离临时检出和独立 venv 实跑；未运行账号镜像或Windows。标准库 tomllib 为独立语义对照，不用候选自身 parse 给自身作唯一裁判。20步未实施。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
