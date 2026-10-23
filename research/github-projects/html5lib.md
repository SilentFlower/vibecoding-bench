# 真实项目审查：html5lib

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[html5lib/html5lib-python](https://github.com/html5lib/html5lib-python)；官方API返回的canonical full_name、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json与commit.json。
- 完整提交：[fd4f032bc090d44fb11a84b352dad7cbee0a4745](https://github.com/html5lib/html5lib-python/tree/fd4f032bc090d44fb11a84b352dad7cbee0a4745)。
- 许可证：MIT。实读根LICENSE（James Graham及贡献者）；原生测试子模块html5lib-tests也为MIT，单独固定提交9b4a29c943b3c905e46b26569bae16de8b373516并保留其LICENSE。仓库URL以GitHub实际canonical full_name html5lib/html5lib-python为准。
- 用途：按HTML解析规则把可能不规整的文档/片段转为DOM、ElementTree或lxml树，再通过walker、过滤器与序列化器输出。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 137／1416588 |
| 产品 Python 文件／行数 | 52／15648（html5lib/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512m 上限运行 |
| 安装 | 6.56（首次阶段；后续补装未测总墙钟） 秒，venv 66456388 字节（含本轮测试依赖） |
| 原生基线 | 23563 主项通过、0 失败、0 错误、6038 普通跳过、1017 预期失败、73 警告；JUnit共30618项，聚合skipped7055；墙钟 39.224 秒，exit 0 |
| 测试峰值 RSS | 272776 KiB（容器测试进程观测） |

运行必需six/webencodings；原生基线另安装lxml/Genshi/chardet全部可选后端及pytest-expect；chardet固定5.2.0以匹配此历史API。首装6.56秒失败，后续补装日志单独保留且未取得总安装墙钟，不将6.56秒冒称全部安装成本；最终pip check与原生完整测试均成功。测试数据单独git子模块，产品源码未改。完整测试512MiB上限峰值约266MiB，普通归档场景另用256MiB。

完整html5lib/tests及固定官方html5lib-tests数据，未裁剪树构建、词法、serializer或adapter集合。6038跳过：5179为Python3中cElementTree与ElementTree别名而上游主动不重复运行，668为已知parser输出不符后不再测下游walker，183为后端data loss warning，8为上游不限定字典属性顺序。1017是上游已有xfail，73警告保留日志；不能表述所有HTML规范都通过。首轮缺pytest-expect的收集失败保留dependency-first-*；补装后完整通过。未跑tox其他Python/最旧依赖矩阵、flake8、coverage或文档构建。

## 源码与真实场景

实际读取公开入口、编码优先级、tokenizer状态、构树phase与treebuilder/walker合同、serializer选项、lint以及原生测试生成器。原版已具备文件流读取、strict/errors、debug日志、编码覆盖/探测、fragment、属性排序与多个后端，路线均说明这些现有能力。两个固定提交缺陷为DOCTYPE标识字段误检name，以及完整lint流结束漏检未闭合栈；其余为新的明确合同或业务增强。现代template及外来命名空间fragment作为兼容增强，不混称既有历史规范缺陷。

在256MiB无网络容器中实跑UTF8中文字节HTML，包含省略p/td结束标签的表格；原版补齐结构并序列化，写入临时archive.html后再次解析，标题归档清单与两格文档/2保持。observe.py同时实证两个lint缺陷并记录20项原版能力边界，加载/source/html5lib/__init__.py，exit0。

完整 [20 步路线](./html5lib-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/html5lib/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/html5lib/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/html5lib/html5lib-python.git <checkout>
git -C <checkout> checkout --detach fd4f032bc090d44fb11a84b352dad7cbee0a4745
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

先git submodule update --init html5lib/tests/testdata，并核对提交9b4a29c943b3c905e46b26569bae16de8b373516；完整基线可用通用run_python_baseline.py baseline <evidence> --memory 512m（完整html5lib/tests），业务用run_python_probe.py <evidence> --memory 256m。requirements-frozen为实际成功依赖，原生工具coverage/flake8未安装且不属于本轮pytest结果。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
