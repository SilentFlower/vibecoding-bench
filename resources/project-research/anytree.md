# AnyTree 单仓研究

2026-10-21：已完成来源、原生基线和[二十步路线](./anytree-roadmap-20.md)研究；未实施路线、制作冻结验收或接入平台。

## 来源、固定提交与许可

官方[c0fec0de/anytree](https://github.com/c0fec0de/anytree)，固定[完整提交](https://github.com/c0fec0de/anytree/tree/2e0a1b956172654d75aff93277ce3d883355e0bf)：`2e0a1b956172654d75aff93277ce3d883355e0bf`。已核对官网仓库、pyproject链接与实际origin，保留Apache-2.0 LICENSE及原源码归属；跟踪源码与测试未另带vendor代码许可，文档图片不作为运行时素材另分发。适用普通分类树、组织树与树的本地进出，不需要外部服务。

## 真实源码与成本

跟踪129文件、569150字节，产品Python源码4056行。读取NodeMixin/LightNodeMixin挂接、children事务回退、迭代器filter/stop/maxlevel、Resolver的get/glob/**及名称匹配、Dict/Json导入导出、RenderTree、缓存包装与util实际定义。commonancestors、左右兄弟、glob递归匹配、属性筛选/子级排序和Mermaid边回调已经存在，不重复列新功能。

宿主Python3.12.3独立venv初装11.704秒，含测试依赖环境55097702字节；运行时零强制第三方依赖，测试安装pytest/cov/test2ref和文档YAML例子所需PyYAML，版本精确冻结。PyYAML为本轮补齐的测试依赖，并非产品运行需求；补装日志保留。系统Graphviz未安装，不冒充图像渲染已验证。

## 适用完整原生基线

实际运行完整`src/anytree tests docs`及模块/文档doctest，**234通过、1跳过、0失败/错误/xfail**，无子测试。命令保留上游doctest和测试数据忽略规则，override addopts只去掉cov/html/report.xml向只读源目录写展示产物，不裁剪业务测试。容器执行Python3.12.15，离线账号镜像UID1000、只读根、512MiB，墙钟1.712秒、pytest 0.967秒、峰值RSS41040KiB。唯一skip为tests/test_dotexport.py需要可选Graphviz dot，其他Python、文档构建、lint/mypy和跨平台矩阵未运行。

第一轮文档YAML例子因缺PyYAML失败，现场在first-attempt；补齐原生依赖后原集合全量复跑通过，不将环境失败算产品缺陷。容器已移除，原检出保持干净。

## 实际场景与20步

真实分类“商品→饮品→茶”通过DictImporter构造、Resolver定位、RenderTree中文展示、JsonExporter/JsonImporter往返，实际模块`/source/src/anytree/__init__.py`。原版观察还验证1100层递归边界、拒绝挂接后的原状态、同名路径选首个、字面斜杠名称不可访问、slots节点默认导出异常，以及共享字典导出器被JSON maxlevel写坏。只有最后一项按共享状态修复计，其余属于明确可选增强。缓存项只核对实现，未装fastcache，不能宣称实证缓存错误。

20步各自定义正常/边界验收和真实回归位置。第09步裁剪副本真正依赖第05步克隆，其他不强造前置；深树、事务、导入、局部编辑、比较、解析和渲染是各自独立交付，不拆测试或重试。新模块名称均为提案。

## 证据与复跑

证据根`.deploy/github-100-research/resume-main/anytree/`含固定源码source、revision/repository、安装日志与freeze、size、baseline-tests.log/xml及结果、observe.py/observations-result.json、roadmap-20/review-result/evidence-sha256。它们是本机可重建证据，不是已发布基线。

新机器从官方clone后固定上述SHA，Python3.12新建venv，安装test-requirements.txt与原生源码，然后在checkout中运行：

```bash
python -m pytest -q -ra -p no:cacheprovider -o 'addopts=--doctest-modules --doctest-glob=docs/*.rst --ignore-glob=tests/testdata/* --log-level=INFO' src/anytree tests docs --junitxml=/tmp/anytree-tests.xml
```

本机观察复跑：`.deploy/github-100-research/resume-main/control/bin/python .deploy/github-100-research/run_python_probe.py .deploy/github-100-research/resume-main/anytree --memory 512m`。正式离线依赖、候选加载适配与控制端独立验收仍未完成；未改正式库、未提交推送部署。
