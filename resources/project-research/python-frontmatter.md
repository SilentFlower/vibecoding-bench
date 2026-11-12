# 真实项目审查：python-frontmatter

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[eyeseast/python-frontmatter](https://github.com/eyeseast/python-frontmatter)；官方API返回的仓库归属、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json与commit.json。
- 完整提交：[d2977d71638cb451bc06f2af3bb48e09e0dbe8c6](https://github.com/eyeseast/python-frontmatter/tree/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6)。
- 许可证：MIT。实读根LICENSE，Copyright 2021 Chris Amico；pyproject的repository URL与官方API full_name eyeseast/python-frontmatter一致。
- 用途：把文本文件中的YAML、JSON或可选TOML元数据与正文分开读取、通过Post编辑，再使用原格式或显式handler导出，适合文档和栏目资料维护。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 56／285921 |
| 产品 Python 文件／行数 | 4／716（frontmatter/） |
| 环境 | Linux；既有原生基线在宿主Python 3.12.3独立venv执行，未施加容器内存上限；补充业务观察单独在Python 3.12.15账号镜像、UID 1000、只读根文件系统、无网络、256MiB上限执行 |
| 安装 | 15.699 秒，venv 53595781 字节（含本轮测试依赖） |
| 原生基线 | 既有默认56项通过；另补CI严格收集的11个doctest通过，合并覆盖67项且互不重复；0失败、0错误、0跳过、0预期失败、0警告；墙钟 0.561 秒，exit 0 |
| 测试峰值 RSS | 30428 KiB（容器测试进程观测） |

必需依赖只有PyYAML；此环境另含可选toml及pyaml和pytest，固定版本见requirements-frozen。mypy/type stubs是静态工具而非本次pytest必需依赖，未安装/运行；Sphinx/Black未跑。安装15.699秒；默认56项墙钟0.561秒、峰值30428KiB；严格doctest补项11项另0.29秒、峰值29564KiB。两者都是宿主运行，未宣称受512MiB或容器隔离；独立业务观察另在无网络256MiB容器运行。

复用原宿主Python3.12.3独立venv的pytest -q -ra -p no:cacheprovider成功56项，未重跑。实际CI命令为pytest . --doctest-modules --doctest-glob README.md；collect-only完整清单67项证明确有11个额外DoctestItem，已仅补跑README、Pandoc/Reverse示例和frontmatter模块这11项，独立XML/log/result均保存。原tests/test_docs.py包装器没有断言doctest失败数，因此补跑pytest原生doctest避免把包装器通过当成严格文档断言通过。baseline-result.json仍如实为56项，doctest-supplement-result.json为11项，不改写原始基线XML。未跑CI的black、mypy及其他Python矩阵。

## 源码与真实场景

实际读完三个核心源码文件，核对Post构造与字典代理、parse/load/loads的规范化顺序、默认handler全局列表、YAML/JSON/TOML识别/切分/导出及IO工具；同时看原生单元/文件fixture/文档包装器和CI。原版已有自定义handler、Pandoc与逆向示例、pyaml美化、格式切换、浅defaults、str/bytes及扁平to_dict，不重计这些能力。三类缺陷均有原版实跑：metadata展开碰构造形参，前导空白下识别结果与实际parse不一致，JSON格式器输出与正则分隔器不自洽；其余为17项独立文档业务/兼容/维护合同。保留空白、严格非映射诊断、层合并等都如实标增强，不把当前有意默认行为称缺陷。

真实中文资料整理周报包含title/author/tags，loads后增加status，dump到临时report.md再load，metadata与正文完全一致。observe.py另记录3类缺陷、非映射/未闭合header、空白/注释变化、浅defaults、日期跨格式和BytesIO边界及20项API观察。业务加载/source/frontmatter/__init__.py，在Python3.12.15镜像256MiB容器exit0，不替代宿主原生基线。

完整 [20 步路线](./python-frontmatter-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-app/python-frontmatter/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-app/python-frontmatter/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/eyeseast/python-frontmatter.git <checkout>
git -C <checkout> checkout --detach d2977d71638cb451bc06f2af3bb48e09e0dbe8c6
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

原56项命令与cwd在baseline-result.json，原样复用未重跑。CI完整收集范围可用pytest . --doctest-modules --doctest-glob README.md --collect-only核对；run_doctest_supplement.py记录仅11项补充的确切命令，doctest-supplement-result.json另记耗时/RSS。业务用含docker SDK的Python运行run_python_probe.py <evidence> --memory 256m。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
