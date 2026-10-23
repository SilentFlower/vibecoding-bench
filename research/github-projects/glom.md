# 候选审查：glom

状态：**未通过适用完整基线，暂不计研究完成**。

官方仓库：[mahmoud/glom](https://github.com/mahmoud/glom)，固定 [fd70d3051a6a1bcb5152ec2d8e2cdc8e852f95e6](https://github.com/mahmoud/glom/tree/fd70d3051a6a1bcb5152ec2d8e2cdc8e852f95e6)，版本25.12.1.dev，BSD-3-Clause，已读取LICENSE并保留归属。

核心为声明式嵌套对象变换，读取core／streaming／mutation／matching／grouping／reduction／cli真实定义，已确认Iter流式转换、Match、Assign/Delete、Group等能力存在。纯本地API运行需boltons、attrs、face，无外部服务；本轮安装test extra和pytest，独立临时检出、HOME和venv。

原版默认pytest **202项全过**。进一步按上游tox要求执行`python -m pytest -q -ra --doctest-modules glom`后，**265通过、1失败、2上游+SKIP doctest跳过**，1.76秒。失败为glom.tutorial示例期望Email(id=5)，实际id=6；与[官方#330](https://github.com/mahmoud/glom/issues/330)的单元测试污染教程共享样例一致。本轮没有修改测试、排除教程或用不含doctest的成功数字冒充完整基线；该问题仍未解决。

原生场景`glom(target, {'names': ('users', ['name']), 'ids': ('users', ['id'])})`从合成用户树抽取中文名字和ID通过，target保留，导入来自冻结源码。适用全套失败不能被这一个使用场景覆盖，所以未继续把20步写成准入路线。

证据：`.deploy/github-100-research/cli-config/glom/`；unit-only-*保留首轮，baseline-tests.log/xml/result.json记录包含doctest的实际失败；observe.py／observations-result.json为场景，repository.json／issues.json／revision.txt／source-path.txt为来源，依赖锁与安装资源另有installation*.json／requirements-frozen.txt。review-result.json明确research_complete=false、roadmap_steps=0。

重跑：clone官方仓库并detached checkout上述commit，独立venv安装`-r <evidence>/test-requirements.txt -e '<checkout>[test]'`，checkout内执行`<venv>/bin/python -m pytest -q -ra --doctest-modules glom`。不运行官方setup.py发布命令或网络服务。未改上游源码、正式项目库或生产数据，未提交／推送／部署或发上游消息。
