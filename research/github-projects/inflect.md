# 真实项目审查：Inflect

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[jaraco/inflect](https://github.com/jaraco/inflect)。
- 固定提交：[99596854bd296af1557db2015cfa98c8104ec155](https://github.com/jaraco/inflect/tree/99596854bd296af1557db2015cfa98c8104ec155)，版本 SCM安装值0.1.dev1+g99596854b（不是发布版本号）。
- 许可证：MIT（pyproject.toml声明）。跟踪源码未含LICENSE，构建coherent.licensed生成MIT文件，已保存build-generated-LICENSE.txt并移走该非跟踪构建副产物。生成文本中的copyright holders为占位，不能冒充上游逐字版权声明；源模块明确Copyright(C)2010 Paul Dyson，分发应连同该归属保留。GitHub API license为null不被写成已识别LICENSE。
- 英语单复数、冠词、分词、词形比较、序数词和数字读法库；纯本地文本处理，无账号、数据库或网络服务。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 62／280540 |
| 产品 Python 模块／行数 | 2／4108（inflect/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 10.49 秒，venv 51429854 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 275 通过、0 失败、0 错误、0 跳过、16 预期失败；另 0 个原生子测试通过；墙钟 3.67 秒 |
| 子进程峰值 RSS | 76344 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

Python≥3.10，运行jaraco.functools、more_itertools和typeguard；测试额外pytest/Pygments。构建setuptools_scm与coherent.licensed可网络预备，本轮依赖和构建副产物均记录；主tox还列风格/类型/覆盖插件，本轮仅验证适用产品行为和原生doctest，不宣称这些检查通过。

最终275通过、16个原生xfail、0普通skip/失败/错误。xfail涉及自定义verb compare、所有格比较/大小写、代词比较与number参数/分组，详见原生日志逐项原因。路线只引用已核对的部分，未把所有xfail各拆一步。

engine保存classical/count/gender和用户规则；plural_noun/_plnoun与singular_noun/_sinoun按词库和模式转换，postprocess恢复大小写，compare系列经_plequal比较。number_to_words先chunk清洗再按group调用enword，ordinal独立加后缀；inflect通过受限方法表处理字符串函数调用。已读真实规则注册/匹配、postprocess、数词管线、article、join、状态和Word类型检查。

## 原生使用场景和改进研究

真实场景生成“2 children saw an owl; forty-two.”，原生冠词/不规则复数/读数组合通过。复现5类修复目标：输入句子导致postprocess IndexError、defverb自定义关系比较失败、所有格比较类别错误、group=2忽略one覆盖、classical非法选项抛错前部分修改状态。冷进程import三次约1.68–1.73秒形成性能基线。Property/Old technology行为可由现有classical(names=False)改变，defnoun(case=preserve)已能输出URLs；mass/business已修复为False，旧单引号输入已不再抛IndexError，这些不虚报为新BUG。现有数字字符串宽松清洗把1e3读成thirteen、abc读成zero，以下以显式严格模式增强处理，不擅自声称旧接口保证数值语法。

完整 [20 步路线](./inflect-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/inflect/`；固定源码当前位置 `/tmp/github-research-inflect-fejvmgzv/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/jaraco/inflect.git <checkout>
git -C <checkout> checkout --detach 99596854bd296af1557db2015cfa98c8104ec155
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>[test]'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；构建生成的MIT许可保留在 `build-generated-LICENSE.txt`，原源码作者归属一并保存。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

独立临时检出、隔离HOME和venv执行，观察只用合成英语文本/数字。性能耗时含解释器启动与当前机器噪声，不能把它当跨机器SLA。以下15项增强是实际工程提案，部分扩大可选读法/词形辅助范围，不暗示上游采纳；仍限定英语，不引入NLP模型/远程词典。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
