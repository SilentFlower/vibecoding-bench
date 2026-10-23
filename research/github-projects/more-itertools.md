# More-itertools：真实项目审查

日期：2026-10-21。官方 [more-itertools/more-itertools](https://github.com/more-itertools/more-itertools)，固定 [4aeb4338ae1407d8da9723e86da99efeb446f719](https://github.com/more-itertools/more-itertools/tree/4aeb4338ae1407d8da9723e86da99efeb446f719)，版本 11.2.1，MIT 许可证，Python ≥ 3.11。源码许可证已读，后续复制须保留版权及许可。

它是处理迭代器、分块、分组、组合枚举、采样和流式统计的真实 Python 库。核心无第三方运行依赖，不需要网络服务、账户或数据集；运行轻，API 面较宽，不能当作几十行练习程序。实际跟踪 39 文件、692,033 字节，产品三个 Python 模块共 7,267 行：more.py 5,644、recipes.py 1,617、__init__.py 6。更多测试和文档不计入产品行数。

## 成本与基线

独立 venv 安装源码和 pytest 用时 12.929 秒（含环境准备／网络），环境约 50.2 MB。完整上游 tests 在 V3 account 镜像 `v3-ci-39482854683-1` 离线、非 root、只读源码／根文件系统、无账号目录、256 MiB RAM、PID 128 中执行：**765 主项通过，另 21,194 子项通过，0 失败／错误／跳过**。JUnit 总记录 21,959，不冒充 21,959 个独立测试函数。

pytest 88.164 秒，容器整体 90.410 秒；进程 ru_maxrss 265,340 KiB 是进程观测口径，与 cgroup 内存计费不同，不能据此把预算说成更大。容器没有 OOM，清理后已确认删除。首轮研究调用预算 60 秒被中断，后续扩大研究等待预算后完成，未改产品超时或上游测试。完整测试矩阵较贵，未来单步应选相关回归，阶段末再跑完整集合。

没有运行 ruff、类型桩验证、Sphinx 或多 Python／多平台矩阵。测试依赖版本见证据目录冻结文件；核心运行依赖仍为空。

## 源码与实际使用

已读取 more.py／recipes.py 的导出、相关函数和 seekable、bucket、sized_iterator、concurrent_tee 的定义。典型路径是用户的一次性 iterator → chunked／groupby_transform 等惰性操作 → 实际消费结果；一些分区、采样或统计函数会按其文档缓存数据，不能宣称全库常量内存。

原生使用场景：把一次性文本数值流转换为整数，分成两项批次，实际得到 `[[1,2],[3,4],[5]]`，总和 15。原版观察实际导入冻结检出：空集合 set_partitions 返回 `[]`；partition 的重入谓词让真分支成为 `[2,1]`；9 项且 max_size=1 时只返回一个分区，却调用递归 helper 36,696 次。增强缺口通过导出／签名和已读实现核对。

已验证旧 issue #1268 在该提交**已经修复**：maxlen=0 的 seekable 经 peek 和 bool 后仍完整返回 `[10,20,30]`。它只作为回归对照，未计成新 BUG。[20 步路线](./more-itertools-roadmap-20.md) 为 2 个已复现修复和 18 个性能／功能增强方案；大部分增强是具体流处理场景提案，不冒称上游同意。

## 证据与复跑

证据根 `.deploy/github-100-research/core-utils/more-itertools/`：source 为固定干净检出；repository.json、issues.json、revision.txt 保存官方来源；size.json、installation*.json、requirements-frozen.txt、test-requirements.txt 保存成本和锁定环境；baseline-tests.log／xml、baseline-result.json 为完整离线测试；observe.py／observations-result.json 为原生场景、缺陷和已修复对照；roadmap-20.json、review-result.json、evidence-sha256.json 为结构化清单及摘要。

重跑先 clone 官方仓库并 checkout 上述完整提交，独立 venv 安装冻结测试依赖和该源码，运行 `python -m pytest -q -ra tests`；原版观察执行该 venv 的 Python 加证据目录 observe.py。完整复用隔离机制见 `.deploy/github-100-research/run_python_baseline.py`，它只做执行取证，不生成项目源码或路线内容。临时依赖环境不放入项目快照。

研究完成不等于功能完成：未实现二十步、未冻结独立验收、未适配现有 app.py verifier、未入正式库。未修改产品／上游源码或生产数据，未提交／推送／部署／发上游消息，模型业务测试与生产请求为 0。
