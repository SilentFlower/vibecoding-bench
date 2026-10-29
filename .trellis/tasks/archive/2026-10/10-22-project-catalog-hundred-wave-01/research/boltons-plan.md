# Boltons真实批处理与数据清理场景设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](boltons-admission.json)为准。

## 来源和已读定义

固定 `mahmoud/boltons@4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d`，完整113文件与BSD许可保留。已完整读取unique／unique_iter／redundant、chunked／chunked_iter、remap、get_path和JSONLIterator的相关实现与真实测试导入。当前镜像678主项全过，其中153个doctest，另12子项通过；冻结文档按真实动态导出名恢复。

## 四场景十任务

| 场景 | 任务 | 业务问题与合法结果 | 实际原生事实 |
| --- | --- | --- | --- |
| BO-S01 重复项报告 | BO-U01 理解 | unique与redundant返回哪个原值、分组怎样排序 | 首次出现／首次重复／完整分组按实际输入对账 |
| BO-S01 | BO-C01 咨询 | 用已有key做大小写归一化并保留业务原值 | str.lower或显式业务字段key；不把归一化值误当返回值 |
| BO-S01 | BO-D01 诊断 | 合法但bool为False的callable为何被忽略 | 验证接受callable，但执行用truthiness分派 |
| BO-S01 | BO-M01 修改 | 只把None作为缺省key，支持falsey callable | 原版失败、参考通过、仅修非分组路径反例拒绝及完整原生回归 |
| BO-S02 批次消费 | BO-U02 理解 | chunked_iter惰性与尾批填充 | 首次消费只读取一批，fill=None是显式填充值 |
| BO-S02 | BO-P01 方案 | 规划有限输入的本地批处理、失败和提交 | 明确批大小、最后一批、已提交前缀和源错误，不承诺全局去重恒定内存 |
| BO-S03 嵌套记录 | BO-U03 理解 | remap只删None时是否误删0、False、空串 | 实际递归新对象与原记录保持 |
| BO-S03 | BO-C02 咨询 | get_path的缺失、None和默认如何区分 | 唯一哨兵、显式默认及真实PathAccessError，无需改库 |
| BO-S04 JSONL导入 | BO-U04 理解 | strict／ignore_errors／reverse的实际记录顺序 | 真实字节流与坏行、空行消费 |
| BO-S04 | BO-P02 方案 | 规划坏行策略和可审计本地导入 | skip便利不等于逐行审计API，需要时应用逐行解析并记录位置 |

九项非修改、一项修改，requires均为空。重复项场景有normal、diagnose_only和modify_direct，其他完整公开材料不制造取证分支。

## falsey key修复合同

仅授权 `library/boltons/iterutils.py` 与 `library/tests/test_iterutils.py`。保留公开签名、None默认、普通callable、属性名shorthand、重复项原值／分组次序和错误传播；合法callable即使__bool__为False或__len__为0也必须使用，包括可将非哈希记录归一化的key。不能把自定义key转换成bool或对输入排序，不改其他迭代工具和控制文件。

公开新增测试覆盖普通和groups=True路径，原版失败／参考通过；仅非分组修复不能通过独立矩阵。原版完整678节点及153doctest／12子项独立保留。当前为业务设计，实际原生与产品链通过前不计正式内容。
