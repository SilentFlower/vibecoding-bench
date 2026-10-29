# 验收严格性初审

## 覆盖与证据等级

已静态读取 100 个项目的原生合同与 600 个工程目标实际引用的 594 个业务观察器；原生回归器有 45 种字节版本，16 个项目包含子测试合同。完整入口、摘要与风险信号保存在 `inventory.json`。这里只对下列已经人工核对公开材料及实现的条目给出语义结论，静态扫描命中不等于缺陷，也不表示全部目标已经逐项动态复验。

线上只读扫描了普通 Projects 的 193 份提交报告及工程养号的 4 份报告：当前可见合同记录不匹配涉及 Docutils 的子测试，以及已通过目标 Arrow 的旧原生集合报告。没有从汇总结果推断所有历史失败都属于同一种误判。Docutils 两份报告的精确对比保存于 `docutils-production-evidence.json`。

## 已确认需要修正

| 编号 | 条件与影响 | 证据 | 修正方向 |
| --- | --- | --- | --- |
| V001 | Docutils 把无业务含义的文件遍历顺序当作必须保持的行为；已经导致两次线上误拒 | 上游 `project_library/projects/docutils/seed/library/docutils/test/test_functional.py:103`；冻结回归器 `project_library/projects/docutils/verification/native_regression.py:1050`；线上 1776 条子项去掉 ordinal 后多重集合完全一致，仅 39 条位置不同 | 原始证据保留执行序号；比较原生子测试身份、上下文和结果的多重集合，不比较偶然执行次序；业务输出本身的顺序仍由测试验证 |
| V002 | 冻结子测试把 Python 对象默认 repr 的进程内存地址当作固定身份 | `inventory.json`：more-itertools 31 条、pyparsing 6 条、wrapt 8 条，共 45 条；`orchestrator/project_native_regression.py:1354` 将参数 repr 保存为上下文，`:1877` 完整比较 | 仅归一化已核实父测试/参数位置中的默认对象或函数 repr 地址；保留类型、函数名、普通字符串、数值及字面量。SQL 中的 `0x1234` 等业务数据不能被替换 |
| V003 | Webcolors 新增 Palette 必须使用名为 `_colors` 的私有存储，拒绝使用其他字段或不可变结构的等价实现 | `project_library/projects/webcolors/verification/WEBCOLORS-06-DEV-observe.py:25`；公开合同与测试均只要求不可变 Mapping、输入/输出隔离及实际转换行为，没有指定该字段 | 通过 Mapping 接口、输入修改、to_dict 返回值修改及独立实例验证不可变/隔离；不要求私有存储名称 |
| V004 | Bibtexparser 的未知规则版本拒绝被收窄为唯一 ValueError | `project_library/projects/bibtexparser/verification/BIBTEXPARSER-O02-DEV-observe.py:29`；对应合同只要求拒绝 unsupported rule versions，公开测试未规定异常子类 | 在这一个无效参数检查点兼容合理的参数/版本拒绝异常；正常验证输出与原数据不变仍必须满足，普通开发异常不充当合法拒绝 |
| V005 | Click 写入工具对软链接的拒绝被收窄为唯一 ValueError，合理 OSError 类拒绝也被失败处理 | `project_library/projects/click/verification/CK-STABLE-WRITE-DEV-observe.py:21`；公开合同只要求 reject symlinks；公开测试中的 OSError 要求针对 replace 失败传播，不能混淆 | 在软链接拒绝检查点兼容合理拒绝类型；继续验证原文件字节/权限、链接和临时文件收口，真实写穿链接必须失败 |

V002～V005 已确认规则对实现施加了不必要限制，但未声称存在对应线上候选误拒记录；实施时仍须用原版、参考、合理替代和真实错误四组案例动态证明修正有效。

## 实施与动态验证结果

- V001～V005 已修复；续查另外修复了 Liquid 必须使用 `_cache` 的私有存储限制（V006），改为真实命中、容量/LRU 淘汰、旧模板快照和异步新版本检查。
- V007：more-itertools 冻结子测试 JSON 实测 4,041,567 字节，超过原 2 MiB 结果及日志上限，首次禁网复验因准备标记被日志轮转丢弃而报环境错误。已按冻结合同规模计算有限预算（结果至少 2 MiB、至多 16 MiB），为 Docker JSON 转义预留日志容量；复验完整通过。
- 原线上 Docutils 候选摘要 `a5d9a63a1edb8a640e9b5c90032c464f08733e519563001c719bfbcfe4a40217` 重建一致，业务检查通过，完整回归 457 通过、2 跳过；more-itertools 765 通过，pyparsing 2175 通过，wrapt 1412 通过、6 跳过，均无失败/错误，子测试合同比较全部通过。
- Palette、Bibtexparser、Click、Liquid 四项观察器的原版/参考/合理替代/实际错误共 16 个真实禁网场景全部符合期望；合理替代通过，真实错误仍被拒绝。
- 单元回归 106 项执行成功（1 项已有跳过）；完整汇总见 `isolated-verification.json`。只读生产取证与本地禁网验证均未改生产状态，尚未声称线上已发布或完整语义评审通过。
- 逐项信号处置见 `signal-disposition.json`：71 个具体异常处理目标、39 个私有访问目标已经按公开材料和代码语境分类；24 项仍保留为需要完整等价候选动态验证的线索，没有统一放宽或宣称全部 600 个目标已经动态验证。

## 同类风险与进一步核对

- 原生 `unittest_skips` 目前按整份列表比较，只有部分官方双轮入口提前排序；见 `orchestrator/project_native_regression.py:1879`。比较时应忽略记录顺序，同时保留跳过身份、原因与重复次数。没有观察到此次 Docutils 因该项失败，不把风险写成线上已发生事实。
- 600 个目标中有 71 个目标出现公开材料未直接提及的具体异常处理分支。逐段复核后，这些分支中同时存在：真正收窄无效参数拒绝的规则、用于核实调用方原异常传播的注入异常、原生 API 既有异常、解析器自身辅助处理，以及单纯在正常路径捕获失败。不能把这 71 项统一改成 `except Exception`。
- 39 个目标有非控制端的私有属性访问。部分属于公开承诺或固定原生 API，例如 Icecream 的 `_enter_time` 兼容和 attrs 的真实字段身份；部分是替代行为检查的实现假设，例如 Palette 的 `_colors`。实施中按公开行为逐项判定，不能仅按下划线扫描结果删除检查。
- `IF-TEMPLATE-DEV` 的缺字段检查要求 `error.args == ('missing',)`，而公开材料只要求预先检查必需名称：应进一步用合理消息表示变体和正常/缺失输入验证，不直接把所有异常当成功。
- `JM-ITER-DEV` 在首次迭代后修改 Options，再要求后续结果仍为完全相同的 OrderedDict 类型；公开合同有 compile/bind once，但未单列外部可变 Options 的快照细节。先核继承 API 和公开材料，当前不把该项擅自改成另一种产品语义。

## 已有兼容与应保留的严格项

| 项目/机制 | 核对结果 |
| --- | --- |
| 主测试节点排序 | 当前公共回归器先按节点身份排序再比较，不存在直接依赖收集顺序的问题，见 `orchestrator/project_native_regression.py:1827` |
| SQLGlot 大量子测试 | 已有特定多重集合和 PointClass 地址归一化，重复次数和 SQL 字面量继续受保护，见 `orchestrator/project_native_regression.py:1076` |
| Python 补丁版本 | 已默认按主次版本兼容；实际镜像 3.12.16 与冻结 3.12.15 的差异没有阻止此次 Docutils 运行。第三方测试插件身份和完整性另有作用，不等同于业务实现细节 |
| `_same_json` | JSON 对象不依赖键顺序，数字已有容差；双布尔验收标记的严格类型用于受控报告协议，不能把字符串或数字当通过。业务列表顺序不能统一抹掉 |
| 独立模型评审 | 已要求接受简洁/功能等价回答，不按长度或关键词打分；单个完整 JSON 代码块及匹配元数据已有兼容，身份/证据/矛盾结论仍需检查 |
| agate reference_datetime | 公开合同明确要求 TypeError，不能因“异常类型严格”一律删除，见对应 `AG-REFERENCE-DEV-contract.md` |
| Inflect clone / Box pickle | 公开合同明确要求保留实际具体子类，类型身份检查有依据 |
| Toolz / Pluggy / attrs | 公开合同明确要求未改分支引用、浅复制或原异常对象；相应 `is` 检查用于业务要求 |
| Markdownify | 公开示例明确写出 Markdown 结果，内部空白/换行影响内容；不通过全局 strip 或压缩空白处理 |
| 原版测试完整性与授权 | 测试身份、重复次数、结果、候选导入来源、修改范围和历史目标回归必须继续验证 |
| 公开测试执行数 | 595 份 public native 规格带固定执行数，另外 5 份使用既有标志协议；主要用于参考内容准入工具。当前 `ProjectsVerification.__call__` 未直接执行 public_native，不能把这个计数误报成线上本次失败原因 |

## 修正的验证要求

1. 无序元数据允许重排；删除、追加、重复次数变化、失败变跳过等记录变化仍拒绝。
2. 默认 repr 地址变化允许；对象类型、父测试、参数业务值、函数名或 SQL/十六进制字面量变化仍拒绝。原始观察文件保持不变。
3. 观察器使用原版失败、参考通过、符合公开合同的替代实现通过、邻近真实功能错误失败四组验证，不只测试字符串替换函数。
4. 已冻结工作通过严格来源识别的临时可信副本执行，审计记录原始/有效摘要；不覆盖原合同、脚本或历史报告。
5. 首先修正平台规则，再用原冻结候选经过真实 `verify_native` 禁网入口复验；离线通过、源码交付、线上发布与完整语义评审分别报告。
