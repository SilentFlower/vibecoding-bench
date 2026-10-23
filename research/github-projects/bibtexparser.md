# 真实项目审查：bibtexparser

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[sciunto-org/python-bibtexparser](https://github.com/sciunto-org/python-bibtexparser)；官方网站／项目元数据与 GitHub commit API 已交叉核对，原始内容见 repository.json、commit.json。
- 完整提交：[af329ca482b29691caff69cb2f8e6099670a105f](https://github.com/sciunto-org/python-bibtexparser/tree/af329ca482b29691caff69cb2f8e6099670a105f)。
- 许可证：MIT。实际读取LICENSE与项目元数据，保留Michael Weiss版权、MIT许可及免责。当前研究的是v2.1.0源码，不能套用v1解析器的字段与接口。
- 用途：解析、整理并写出BibTeX文献库，保留条目、字符串宏、注释、失败块及中间件元数据。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 89／496265 |
| 产品 Python 文件／行数 | 18／4184（bibtexparser/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512MiB 上限运行 |
| 安装 | 14.712 秒，venv 53583610 字节（含本轮测试依赖） |
| 原生基线 | 2,819 通过、0 失败、0 错误、12 跳过；墙钟 5.335 秒，exit 0 |
| 测试峰值 RSS | 59584 KiB（容器测试进程观测） |

产品依赖pylatexenc~=2.10，无外部服务、文献数据库或凭据。本轮安装pytest、pytest-cov、pytest-xdist；没有为未验证的笔记本安装整套Jupyter。完整基线512MiB离线容器运行，峰值约58MiB。

原生终端另有4条测试主动触发旧parse_stack/append_middleware参数的DeprecationWarning，日志完整保留。完整默认pytest发现集2,831项；10项为无enclosing可移除而按上游条件跳过，2项为姓名末尾反斜线的逆性质不成立而按上游标记跳过。未删除测试。未运行jupyter示例笔记本、Sphinx构建、跨Python矩阵或覆盖率门槛；这些不称通过。

## 源码与真实场景

读取Library.add/remove/replace的重复键与索引合同、Entry/Field的真实字段与修改语义、parse_string向已有库添加时的宏种子逻辑、write_file/write_string的copy/inplace约定和BibtexFormat选项。中间件已有名称拆分、LaTeX编码、月份、字段排序、宏解析，不能重新计数。interpolate.py的反向宏提取与crossref TODO形成直接增强来源；write_file整串读写和writer重排是流式/保留源需求的依据。README提到crossreference只是架构示意，公开中间件及实跑子条目没有提供解析继承。

实跑含中文title、两位作者（包含组织作者）和@string期刊宏的文献，SeparateCoAuthors/SplitNameParts后再由MergeNameParts/MergeCoAuthors写出；write_file在/tmp生成真实.bib，parse_file重读title、journal和引用key保持，failed_blocks为0。另记录crossref未继承和反向宏未提供的原版行为及其余公开入口缺口。加载/source/bibtexparser/__init__.py，业务场景exit0。

完整 [20 步路线](./bibtexparser-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/bibtexparser/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/bibtexparser/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/sciunto-org/python-bibtexparser.git <checkout>
git -C <checkout> checkout --detach af329ca482b29691caff69cb2f8e6099670a105f
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

完整基线命令`<含docker SDK的Python> <evidence>/run_python_baseline.py baseline <evidence> --memory 512m`；业务观察`<同一Python> <evidence>/run_python_probe.py <evidence>`。默认pytest集合以固定源码tests为准。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

本研究只处理普通文本／文档功能。未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
