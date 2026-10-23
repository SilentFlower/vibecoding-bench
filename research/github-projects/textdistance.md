# 真实项目审查：textdistance

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[life4/textdistance](https://github.com/life4/textdistance)；官方公开仓库页面、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json、commit.json和official-repository.html；匿名API限流时未伪造API结果。
- 完整提交：[d6a68d61088a40eef5c88191ccf79323dbf34850](https://github.com/life4/textdistance/tree/d6a68d61088a40eef5c88191ccf79323dbf34850)。
- 许可证：MIT。LICENSE保留Copyright2018 @orsinium、MIT许可及免责；README/git及GitHub元数据确认life4/textdistance同一上游，setup.py中的orsinium历史URL不计为另一项目。
- 用途：提供编辑、token、序列与压缩等距离/相似度算法，用于本地文档文字比较。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 72／171560 |
| 产品 Python 文件／行数 | 14／2657（textdistance/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512m 上限运行 |
| 安装 | 20.693 秒，venv 139307523 字节（含本轮测试依赖） |
| 原生基线 | 430 主测试通过、0 失败、0 错误、0 跳过；墙钟 21.982 秒，exit 0 |
| 测试峰值 RSS | 270768 KiB（容器测试进程观测） |

核心可纯Python、无服务或凭据。本轮完整external集合安装多个本地C扩展wheel及numpy/Hypothesis；额外安装记录为install-extras.json/log与install-pylev.json/log，最终冻结清单为准。主安装20.693秒，额外阶段总墙钟未取得，不把它当完整安装总时长。测试512MiB预算、RSS270,768KiB。

完整默认pytest集合，包括Hypothesis性质测试和所有注册external库对照。首次只装test依赖导致30项外部库缺失，后extras仍缺pylev有6项失败；原始日志/调整清单保留。按源码benchmark测试要求补齐注册库（rapidfuzz/Levenshtein/jellyfish/pyxDamerauLevenshtein/pylev及numpy）后完整430项通过、终端无警告，未删选。中间一次240秒预算超时日志baseline-timeout.log保留；最终有600秒预算但实际21.982秒完成。未跑benchmark性能排名、mypy/flake8或其他Python矩阵。

## 源码与真实场景

读取Base的归一化/quick_answer/外部库选择、qval准备与Counter，Levenshtein、Hamming、LCSSeq/LCSStr及MongeElkan核心路径，以及公开工具和依赖适配。四项实证为LCS自定义谓词路径不一致、词/qgram重建异常、words_combinations访问不存在equality属性、module/安装版本不一致。已有30多种算法、qval、归一化、numpy可选与自动backend不重新计数；其余增强以比较工作流为完整交付，不用20个算法名字或测试维度填数。

实跑guide/guied的Levenshtein为2、Damerau为1；词级Jaccard比较颠倒词序为1；相同中文文档归一化相似度为1，并逐个比较三个真实文档名候选。观察另外保存四类源码边界的输出/异常。确认加载/source/textdistance/__init__.py；已安装dist元数据来自同一固定源码，不因运行版本字符串不一致而误计为别的项目。普通业务256MiB离线通过。

完整 [20 步路线](./textdistance-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/textdistance/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/textdistance/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/life4/textdistance.git <checkout>
git -C <checkout> checkout --detach d6a68d61088a40eef5c88191ccf79323dbf34850
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

完整基线命令`<含docker SDK的Python> <evidence>/run_native.py baseline <evidence> --memory 512m`；业务`<同一Python> <evidence>/run_python_probe.py <evidence> --memory 256m`。依赖需包含本轮冻结的全部已注册外部库；Hypothesis数据在容器临时副本，原源码只读。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
