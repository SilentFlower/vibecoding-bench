# Treelib 单仓研究

2026-10-21。来源、适用完整原生基线和[20步路线](./treelib-roadmap-20.md)研究完成；未实施路线、冻结独立验收或接入平台。

## 官方来源与许可

官方[caesar0301/treelib](https://github.com/caesar0301/treelib)，固定[完整提交](https://github.com/caesar0301/treelib/tree/83b3b87eaa7c56c9c7b86d19b2eede5252a1b482)：`83b3b87eaa7c56c9c7b86d19b2eede5252a1b482`，项目版本1.8.0。官方网页、pyproject homepage/repository与真实origin一致。Apache-2.0；保留LICENSE里2011 Brett Alistair Kromkamp与2012—2025 Xiaming Chen及贡献者归属、AUTHORS和原文件声明。跟踪运行源码和tests未另列vendor许可；不将文档素材另作产品资源分发。

用途是有节点标识的本地树结构库。与AnyTree的父节点混入模型不同，Treelib由Tree维护id索引，Node按tree_id保存多个视图的父子指针，研究围绕这一真实模型。

## 规模、依赖和源码

47跟踪文件、441516字节，产品Python模块3042行（包含大量原生API文档，不等于纯算法行数）。运行依赖six，无独立服务、数据库或前端构建。宿主Python3.12.3独立venv初装10.364秒，含pytest/cov与six的测试环境51892865字节，精确依赖冻结在requirements-frozen.txt。初装受本机缓存影响。

已读Tree/Node构造、节点id修改、from_map/from_json、to_dict/to_json、expanded、merge/paste、_clone、subtree/remove_subtree、遍历与关系指针方法。已有deep复制、sort、from_map、with_identifier、subtree、move、rsearch/ancestor均不当作新能力。新复制模式强调节点与data不同所有权，新快照强调完整版本化状态，而非改名既有方法。

## 实跑原生基线和场景

上游完整tests原样执行，含性能、comprehensive、I/O及边界集合：**211通过、0失败/错误/跳过/xfail**，无subtests。21条原生warning包含旧bpointer/fpointer与INSERT兼容弃用，保留在原始日志。命令pytest -q -ra -p no:cacheprovider --junitxml=/tmp/results.xml tests，容器执行Python3.12.15，离线只读容器UID1000、512MiB，墙钟2.291秒，pytest 1.315秒，RSS47356KiB；容器已移除。其他Python/OS、文档构建、lint/mypy和独立外部基准未跑。

真实“商品→饮品→茶”构造了id与quantity=2的data，带id/data JSON往返后父级和数量相符；实际加载/source/treelib/__init__.py。原版逐项观察实证：改id覆盖已存在节点并产生重复指针；from_map静默遗漏孤儿；子类from_map返回基类；默认单叶JSON不能由自身from_json读取；折叠显示节点导致所谓整树JSON遗漏后代。五项修复分别对应不同根因/公开契约，其余15项是显式增强。merge局部应用为已观察的旧语义，新增原子模式不冒充原版已承诺事务。

## 路线、证据和重跑

20步各自有正常/异常验收、真实模块、兼容与回归。没有强造功能依赖，部分新功能可以复用复制或快照，但验收可独立定义。所有验收目标都是未来实现要求，不等于本轮已运行的新功能。

本地证据根`.deploy/github-100-research/resume-main/treelib/`，含source、revision/repository、installation与成本、freeze、size、baseline-tests.log/xml与结果、observe.py/observations-result、roadmap-20/review-result/evidence-sha256。新的机器需从官方重新检出上述SHA，用Python3.12新建venv安装test-requirements.txt和原生包，再在checkout运行原生pytest命令。

本机复跑：

```bash
.deploy/github-100-research/resume-main/control/bin/python .deploy/github-100-research/run_python_baseline.py baseline .deploy/github-100-research/resume-main/treelib --memory 512m --tests tests
.deploy/github-100-research/resume-main/control/bin/python .deploy/github-100-research/run_python_probe.py .deploy/github-100-research/resume-main/treelib --memory 512m
```

证据是本地可重建资源，不是跨机器基线发行物；候选加载、离线依赖分发和独立冻结验收尚待接入开发。正式项目库未修改，未提交推送部署。
