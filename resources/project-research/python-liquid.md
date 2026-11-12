# 真实项目审查：Python Liquid

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[jg-rp/liquid](https://github.com/jg-rp/liquid)；官方公开仓库页面、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json、commit.json和official-repository.html；匿名API限流时未伪造API结果。
- 完整提交：[878f589adff6cb6bf08ccea7895570f96980248e](https://github.com/jg-rp/liquid/tree/878f589adff6cb6bf08ccea7895570f96980248e)。
- 许可证：MIT。实读根LICENSE，Copyright 2020–2023 James Prior。完整合规数据来自官方jg-rp/golden-liquid子模块65c2f76ea64ef20647c295b000df5fcd9fc471cd，也实读其MIT LICENSE（2021–2025 James Prior）。
- 用途：在Python中解析和渲染Liquid模板，支持自定义过滤器、标签、多种loader、同步/异步运行和静态分析，适合报表、邮件与文档生成。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 286／1285974 |
| 产品 Python 文件／行数 | 91／15643（liquid/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512m 上限运行 |
| 安装 | 18.344 秒，venv 95297868 字节（含本轮测试依赖） |
| 原生基线 | 3526 主项通过、165 subtests通过、0 失败、0 错误、72 普通跳过、0 预期失败、0 警告；JUnit聚合3691通过/3763项；墙钟 20.482 秒，exit 0 |
| 测试峰值 RSS | 299228 KiB（容器测试进程观测） |

无外部服务。运行依赖MarkupSafe、python-dateutil、Babel、pytz及importlib-resources；本轮测试另装pytest及mock/timeout/cov、Hypothesis和PyYAML，完整版本见requirements-frozen。原生512MiB峰值299228KiB，墙钟20.482秒；普通模板业务在另一个256MiB容器成功。子模块数据单独记录，不计第二项目。

按pyproject默认test=pytest运行完整原生集合，含官方golden-liquid合规数据。72跳过中70为上游TODO，2为Ruby behavioral quirk；165子项不重复计入3526主项。最初未拉子模块导致collection错误保留submodule-first-*；原.gitmodules使用SSH，首个SSH拉取失败日志保留，随后只改本地git config到同一官方HTTPS URL并核对固定gitlink，完整成功。未跑coverage95%门槛、mypy、Ruff、docs、性能脚本及其他Python矩阵。

## 源码与真实场景

已读Environment/BoundTemplate/RenderContext实际合同、loader缓存键及源加载顺序、AST与词法空白处理、静态分析作用域/partial遍历、过滤器注册、输出buffer和翻译提取。原版已支持异步、TextIO写出、变量及标签分析、LRU/自动重载、模板继承和多语过滤器，路线不重复计这些原能力。第01项是源码参数顺序与真实同步/异步对照共同证明的缺陷；第02项把DictLoader缺uptodate的现行为如实标为版本化增强。其余为模板开发与资料业务的独立交付。

真实中文资料周报使用DictLoader、for循环和render子模板；同步与async输出均为资料周报及文档2/图片3两行，写出临时report.txt再读保持。原版静态分析返回title/items全局路径。独立命名空间缓存对照同步成功而异步TemplateNotFoundError，保留错误模板名docs/note；此外记录字典模板更新后仍旧结果和20项源码能力边界。加载/source/liquid/__init__.py，业务exit0。

完整 [20 步路线](./python-liquid-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/python-liquid/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/python-liquid/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/jg-rp/liquid.git <checkout>
git -C <checkout> checkout --detach 878f589adff6cb6bf08ccea7895570f96980248e
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

安装后git -C <checkout> config submodule.tests/golden-liquid.url https://github.com/jg-rp/golden-liquid.git，再git submodule update --init并核对65c2f76ea64ef20647c295b000df5fcd9fc471cd；不改tracked .gitmodules。完整基线用run_native.py baseline <evidence> --memory 512m，临时副本供原生写入；业务用run_python_probe.py <evidence> --memory 256m。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
