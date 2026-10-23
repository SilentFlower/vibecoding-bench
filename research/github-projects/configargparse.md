# 真实项目审查：ConfigArgParse

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[bw2/ConfigArgParse](https://github.com/bw2/ConfigArgParse)。
- 固定提交：[3ab2f323abcdd321b6c423f9eb6304ce35681307](https://github.com/bw2/ConfigArgParse/tree/3ab2f323abcdd321b6c423f9eb6304ce35681307)，版本 固定commit源码；浅检出SCM安装版本0.0.post1.dev1+g3ab2f323a，非官方发布号。
- 许可证：MIT。保留LICENSE中2015 bw2版权、许可和免责声明。
- argparse兼容CLI解析器，融合显式CLI、环境、配置文件和默认值，并能导出配置；核心单模块，无服务或凭据。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 17／315991 |
| 产品 Python 模块／行数 | 1／2344（configargparse.py） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 16.59 秒，venv 65399660 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 164 通过、0 失败、0 错误、0 跳过、5 预期失败；另 226 个原生子测试通过；墙钟 0.99 秒 |
| 子进程峰值 RSS | 91432 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

核心运行零依赖，Python≥3.6；YAML和TOML为可选PyYAML/toml依赖。本轮安装上游测试需要的mock、black、pytest、pytest-cov和pytest-subtests，精确版本冻结；未执行pydoctor/zizmor、全平台／多Python矩阵或部署。

没有普通skip；5为原生已标记预期失败，在baseline-tests.log保留。最终无未预期失败。pytest主测试与子测试分开统计，完整原始XML保留。

ArgumentParser继承argparse，parse_known_args把配置和env值转成真实argv，再用原argparse动作转换，并保存_source_to_settings来源表。ConfigFileParser有default/INI/YAML/TOML/Composite，write_config_file先serialize后打开输出。已读真实构造器、parse_args/known、config转换、来源、write与parser实现。已有default文件列表／glob／callable streams、env_vars注入、auto_env_var_prefix、get_source_to_settings_dict、writeconfig安全门禁、TOML/INI section选择和Composite均不计新增。官方open-issues-only查询为空；路线以固定源码与实际CLI使用缺口为来源，不伪造issue。

## 原生使用场景和改进研究

原生临时配置port5432/name工程，加合成REVIEW_PORT6000、REVIEW_SECRET，再显式--port6432，实际Namespace为6432／工程／synthetic-value，确认候选模块。来源表和format_values实测包含合成值、重复两次取来源返回同一内部对象；default重复port取末值；YAML嵌套server映射变为一个字符串，非自动映射层级；公开parser无JSON专用解析器，parse_result/discover等接口不存在。现状多为当前约定，不误标BUG；20项均为显式增强。

完整 [20 步路线](./configargparse-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/configargparse/`；固定源码当前位置 `/tmp/github-research-configargparse-04b_3kn9/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/bw2/ConfigArgParse.git <checkout>
git -C <checkout> checkout --detach 3ab2f323abcdd321b6c423f9eb6304ce35681307
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>[toml,yaml]'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

只用合成配置／环境并在临时目录运行，未开启HTTP服务、运行setup.py publish/coverage或访问真实配置。已有写配置仅允许真实CLI指定路径的门禁必须回归，任何新功能不能让配置或环境间接设置写出路径。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
