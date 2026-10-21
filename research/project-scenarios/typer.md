# Typer：本地商品 CLI 的真实使用场景样板

## 状态、用途与版本

本文是**场景设计草案**：围绕商品工具的接入、排错、选型和应用开发，编排 4 个业务场景、7 个任务；数量来自业务需要。尚未物化场景夹具、冻结评测、运行模型或接入平台。通用计数、投放与成本规则见[样板总则](./README.md)。

- 上游版本 `V0`：`fastapi/typer@a5882dedf0bc7a46cd861fdfca020f88519e0f21`，Typer 0.27.3。所有场景保持该库源码不变。
- 旧材料：[单仓研究](../github-projects/typer.md)、[20 项增强候选](../github-projects/typer-roadmap-20.md)。这些记录继续保留，本文不重计原有工程改进数量。
- 旧证据：[观察脚本](../../.deploy/github-100-research/resume-app/typer/observe.py)、[观察结果](../../.deploy/github-100-research/resume-app/typer/observations-result.json)、[原生基线](../../.deploy/github-100-research/resume-app/typer/baseline-result.json)。已读取相关定义、上游测试与这些结果，本轮未重跑原生集合。
- 原生旧基线为 1,481 主项通过、22 普通跳过、2 XFAIL；旧商品命令实际输出 `咖啡:3\n`。旧证据支撑现状分析，不能作为本文新增场景已经验收或模型已经完成的证明。
- 夹具中的 `shop.py` 是**用户应用**，不是 Typer 仓库原生文件。下文代码是待物化的夹具规格；`F-*`、`APP-R*` 是设计标识，不是 Git SHA，也不宣称文件已存在。

## 场景索引

| 场景 ID | 用户目标 | 任务 ID／使用类型 | 代码起点与真正依赖 |
| --- | --- | --- | --- |
| TY-S01 | 判断 Typer 是否适合商品工具，并取得接入方法 | TY-U01 理解项目；TY-C01 使用咨询 | V0；两个任务均可独立投放，不依赖前一回答 |
| TY-S02 | 理解命令入口与根选项位置，排除误判 | TY-D01 问题诊断；TY-D02 问题诊断 | V0＋各自全新应用；两任务独立，D02 有真实缺失信息的披露分支 |
| TY-S03 | 确认现有类型能力，为两个商品命令选择方案 | TY-C02 使用咨询；TY-P01 方案讨论 | V0；P01 依赖 C02 的业务事实与回答上下文，无代码变更依赖 |
| TY-S04 | 给用户的商品 CLI 增加本地清单导出 | TY-M01 工程修改 | V0＋独立 APP-R0；不依赖 S01—S03 的回答或代码 |

独立任务可以单独结束。TY-S03 连续投放时累计会话成本；若拆开评测 P01，须补齐 C02 的业务要求与能力事实，不能要求模型知道另一会话的答案。失败重试和同一诊断的补充材料不增加任务数。

## TY-S01：商品工具选型与接入

**隔离与 setup。** TY-U01 提供 V0 源码只读副本、项目说明和依赖版本，不提供用户应用。TY-C01 另建空临时目录，只提供下面这个业务函数；不继承 U01 的回答。两个任务均不允许修改 Typer 或写工作区文件；答复中的最小代码示例可在未来评测端临时执行。

```python
def product(name: str, quantity: int = 1):
    """显示商品数量。@param name 名称。@param quantity 数量。@return None。"""
    print(f"{name}:{quantity}")
```

### TY-U01：理解项目

**用户可见首问：**

> 我想把本地商品处理函数做成命令行工具。这个项目主要解决什么问题？请根据当前源码说明从函数到命令的关键流程，以及它是否会替我存储商品数据。简短说明即可。

**条件追问。** 默认没有；如果答案笼统到无法指导接入，可问“请指出注册命令和实际构造命令分别在哪里”，仍属于 U01 的澄清与补全。

**评测端关键事实与证据。** `Typer` 保存命令注册信息，`command()` 注册函数，`get_command()` 根据注册情况构造命令或命令组；类型注解经 `get_click_param()`、`get_click_type()` 转为参数解析规则。它提供 CLI 构建能力，商品持久化需要用户应用自行实现。依据：[main.py](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)、[models.py](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)。

**通过、失败与结束。** 能解释用途、指出上述关键流程并准确划定数据存储边界即可结束，不要求列出全部内部函数。把 Typer 说成商品数据库、误称当前必须安装外部 Click 才能解析，或编造不存在的商品 API，均失败。全程代码状态仍为 V0＋空应用。

### TY-C01：咨询最小接入

**用户可见首问：**

> 上面是我的商品函数。希望运行 `python shop.py 咖啡 --quantity 3`，默认数量为 1，数量不能为负数。请给出最小可运行的接入示例和调用方式，解释错误输入怎么反馈；先不要替我创建文件。

**条件追问。** 只有示例遗漏默认值、边界或入口时才要求补齐；不预设必须追问，不用额外长报告换取分数。

**评测端关键事实与证据。** 可用 `typer.Typer(add_completion=False)`、`@app.command()`、`Annotated[int, typer.Option(min=0)] = 1` 与 `app()`。一个命令、没有 callback／子组时是单命令模式，调用中不再写函数名。旧商品实跑已经证明中文名称与数量参数的这条路径；非法整数旧观察退出 2。依据：[参数转换实现](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)、[Option 定义](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/params.py)。

**通过、失败与结束。** 未来在临时目录运行答复示例：中文名称和数量 3 得到 `咖啡:3`，省略数量得到 1，0 可接受，负数与非法整数被拒绝；`--help` 不执行商品业务。接口正确、边界符合、说明与行为一致即可结束。误写 `shop.py product 咖啡`、负数被钳制为 0，或实现不存在的 API，均失败。只评答复示例，不将其接受为工作区代码检查点。

## TY-S02：命令模式和选项位置的正常行为诊断

### TY-D01：单命令为什么不写命令名

**隔离与 setup。** 新临时目录提供完整 `F-SINGLE/shop.py`；可只读运行，不允许改应用或 Typer。该夹具按旧商品观察的接口构成，具体文件及新观测输出尚待冻结。

```python
from typing import Annotated

import typer

app = typer.Typer(add_completion=False)


@app.command()
def product(name: str, quantity: Annotated[int, typer.Option(min=0)] = 1):
    """显示商品数量。@param name 名称。@param quantity 数量。@return None。"""
    typer.echo(f"{name}:{quantity}")


if __name__ == "__main__":
    app()
```

**用户可见首问：**

> 代码里注册的函数叫 `product`，但 `python shop.py 咖啡 --quantity 3` 可以直接执行。我以为必须写命令名。这是不是注册失效了？先帮我判断原因，不要改代码。

**条件追问。** 无固定追问；现有材料已足够，不应机械索要缺失信息。

**评测端关键事实与证据。** 单个注册命令，且没有 callback、子组等构组条件，`get_command()` 直接返回单个命令。这是当前正常模式，不是注册失效。若用户日后需要显式命令组，可加 callback 或多个命令，但本任务没有要求实施。依据：[get_command](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)、[单命令构组示例](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/docs_src/commands/one_or_multiple/tutorial001_py310.py)、[对应测试](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/tests/test_tutorial/test_commands/test_one_or_multiple/test_tutorial001.py)。

**通过、失败与结束。** 明确结论“不是 BUG”、依据与当前代码对应、解释实际调用方式即可结束。声称必须修 Typer、把所有单命令应用都说成 group，或未经请求修改源码，均失败。成功结论不会产生代码检查点。

### TY-D02：信息不足时先核对选项归属

**隔离与 setup。** 独立 `F-GROUP`，不复用 F-SINGLE。首轮仅向模型提供固定 Typer 版本和下面的问题；应用文件尚未放入其可读工作区，不能让模型先从文件看到答案再强制澄清。评测端持有待披露夹具，Typer 源码可读。

**用户可见首问：**

> 我给商品工具加了 `--verbose`。运行 `python shop.py export --verbose` 提示 `No such option: --verbose`，这是 Typer 的 BUG 吗？

**真实缺失材料与条件披露。** 首问缺少 callback／命令声明，无法确定选项是根选项、子命令选项还是没有正确注册。模型询问相关注册代码，或请求能确认选项归属的根／子命令 help 后，提供下列完整代码；若先要 help，评测端应从同一夹具生成后提供，不手编帮助输出。

```python
import typer

app = typer.Typer(add_completion=False)


@app.callback()
def root(verbose: bool = False):
    """声明根选项。@param verbose 详细模式。@return None。"""


@app.command()
def export():
    """演示本地导出入口。@return None。"""
    typer.echo("exported")


if __name__ == "__main__":
    app()
```

用户随材料补充：“这是完整注册代码，请据此判断，并告诉我现在应怎么调用。”以上为同一个诊断任务的材料补全，不增加任务数。模型可先提出有条件的可能原因，但不能在披露前断言根因。

**评测端关键事实与证据。** 此时 `verbose` 属于根 callback，当前可用调用为 `python shop.py --verbose export`。TyperGroup 先解析根级参数，再为选中的命令建立子 context；子命令没有声明这个选项。旧观察恰好记录了前置成功、后置退出 2，不证明其他所有选项错误都来自同一原因。依据：[TyperGroup.parse_args／invoke](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/core.py)、[callback 示例](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/docs_src/commands/callback/tutorial001_py310.py)。

**通过、失败与结束。** 先指出信息不足并请求能区分原因的材料；收到材料后给出有依据的无 BUG 结论及正确调用，即可结束。仅提问不算完成；已经给过的固定版本不需要重复索要。首轮武断归因、披露后仍拒绝判断、建议不存在的全局选项开关或擅自改库，均失败。全程不允许写应用代码，代码状态保持 V0＋F-GROUP。

## TY-S03：辨识已有类型能力并选择应用方案

**隔离与 setup。** 新临时目录，V0 只读；不继承前两场景的商品应用。用户需求卡明确：品类仅有字符串 `coffee`、`tea`；SKU 是 `SKU-` 加四个 ASCII 数字；后续两个命令都会接收 SKU。本场景只咨询和讨论，不创建文件，不要求实现上游增强。

### TY-C02：哪些能力已经有

**用户可见首问：**

> 商品品类只允许 `coffee` 或 `tea`，SKU 要解析成我自己的类。这个版本必须改 Typer 才能支持吗？我看到 `Literal`、`parser` 和 `click_type`，请确认它们现在能做什么，以及能不能同时指定后两者。

**条件追问。** 只有答案缺少具体能力边界时补问；不要求模型为已有功能新增测试或实现。

**评测端关键事实与证据。** 字符串 Literal 已映射为 TyperChoice；`parser` 接收字符串并产生用户类型，`click_type` 可提供自定义参数类型，两者都已存在。`ParameterInfo` 明确拒绝同时提供两者。旧观察仅证明 `Literal['coffee','tea']` 能构建成 Choice；完整新业务输入矩阵尚待运行。依据：[类型映射](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)、[互斥检查](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/models.py)、[自定义类型示例](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/docs_src/parameter_types/custom_types/tutorial001_an_py310.py)、[转换测试](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/tests/test_type_conversion.py)、[互斥测试](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/tests/test_others.py)。

**通过、失败与结束。** 正确辨识现有能力、指出互斥并用少量源码依据回答即可结束。不强求某一种表达方式；声称 Literal 不受支持、同时使用两个自定义解析入口，或把“尚无应用级适配注册表”说成“不支持自定义类型”，均失败。回答完成可单独计成功，代码仍是 V0＋空应用。

### TY-P01：两个命令复用 SKU，是否值得改库

**用户可见首问：**

> 我的 SKU 只是 `SKU-` 加四个数字；只有“查询”和“下架”两个本地命令需要它，失败时告诉用户格式不对即可，暂时不需要复杂补全或第三方插件。请比较在应用中复用解析函数、使用自定义参数类型，以及扩展 Typer 注册机制这几种办法，推荐一个维护成本合理的方案。先不要实现。

**条件追问。** 只有推荐方案依赖用户尚未表达的目标时才询问；现有需求已经足以做初步取舍，不要求为了增加轮数追问。

**评测端关键事实与证据。** 可以共享一个 `parse_sku` 函数，在两个参数各自声明 `typer.Option(parser=parse_sku)` 或 Argument；抛出 `ValueError` 会进入参数错误路径，上游测试覆盖该行为。自定义参数类型适合封装更丰富的转换语义；没有应用级注册入口不妨碍本次两个参数复用。依据同 C02，另有[自定义类型行为测试](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/tests/test_tutorial/test_parameter_types/test_custom_types/test_tutorial001.py)。

**通过、失败与结束。** 推荐与两个本地命令的规模相称，说明复用位置、错误反馈与未来扩展代价即可结束。推荐共享 parser 是一个合理答案；有充分约束依据的自定义参数类型方案也可通过。不以唯一措辞或长篇幅评分。臆造 `app.register_type_adapter()`、强迫改框架才能满足现需、忽略已声明 SKU 规则，均失败。不输出或接受代码检查点。

## TY-S04：显式请求给用户应用增加商品导出

**隔离与 setup。** 从全新 `F-SINGLE` 复制商品应用，并在 `@app.command()` 之前加入以下 callback，形成待物化 `APP-R0`。因此 product 已是显式子命令；不存在之前任务完成后自动改过入口的隐含依赖。

```python
@app.callback()
def root():
    """提供商品工具命令组。@return None。"""
```

工作区另提供 UTF-8 `catalog.json`，内容如下。运行时从临时目录导入固定 V0，读取用户应用；冻结端以后应核对实际加载路径，避免装入其他 Typer 版本。

```json
[{"sku":"SKU-0001","name":"咖啡","quantity":3},{"sku":"SKU-0002","name":"茶","quantity":0}]
```

### TY-M01：完整交付一次本地清单导出

**用户可见首问：**

> 现在请修改这个商品应用，增加 `export` 子命令。用 `python shop.py export catalog.json --output result.json` 把商品清单导出为 JSON：保留商品顺序及 sku、name、quantity，忽略其他字段，中文以实际字符保存；输入必须是对象数组，每项都有非空字符串 sku、name，以及非负整数 quantity（布尔值不算整数），重复 sku 拒绝，空数组允许。坏 JSON 或任意无效记录都要非零退出并说明原因，不能留下部分导出文件。已有输出文件拒绝覆盖，输入文件不能改。请同时保留现有 `product` 命令，并补充针对业务行为的测试与简短用法说明。只修改这个用户应用及其测试、文档，不改 Typer 和依赖环境。

这是显式工程修改请求，交付对象是用户应用的 `shop.py`、业务测试和用法文档；**不允许修改 Typer 源码、冻结验收或依赖环境**。输出 JSON 的空白缩进不作为唯一正确格式。

**条件追问。** 需求已给完整核心规则，通常直接实施。若执行环境确实缺材料，应报告具体缺项；评测端不能把基础设施缺失当作业务失败后强迫修改模型代码。

**评测端关键事实与证据。** 当前 `APP-R0` 没有 export 命令；这是新增应用能力，不是修复 Typer 缺陷。`Path` 参数及 `Option` 已受支持，业务 JSON 验证与写文件由应用实现。依据：[Path 与参数映射](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/main.py)、[CliRunner.invoke 与独立 stdout／stderr](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/typer/testing.py)。不要求采用拟议新 API 或某个指定内部算法。

**未来冻结验收入口。** 控制端将用户应用复制到独立临时目录，调用真实进程 `python shop.py …`；核对退出码、stdout／stderr和读取回来的输出文件，不信任应用自报“成功”。用例围绕用户已知规则展开：

- 正常：示例输入成功，输出可被独立 JSON 解析，两个商品顺序、字段值与类型准确，中文文件内容没有被统一转成 `\u` 转义；空数组可导出为空数组。
- 拒绝：坏 JSON、非数组、非对象项、缺字段、空字符串、负数／小数／布尔数量、重复 sku；非零退出且有可理解原因，不产生新输出文件。
- 文件边界：既有输出文件字节保持不变；输入与输出同一路径被拒绝且原文件不变；缺少输入文件返回明确失败。
- 回归：`python shop.py product 咖啡 --quantity 3` 仍输出 `咖啡:3`，默认 1，负数拒绝；root／export 的 `--help` 不生成输出文件。

**通过、失败与结束。** 实际业务与回归全部通过，并核对修改范围后接受用户应用检查点 `APP-R1`；这是将来封存物化文件及摘要后的检查点标识，不是上游新提交。任一规则失败、输入或既有输出被破坏、只打印 JSON 却没有按要求写文件，均不接受检查点。同一任务的失败修复仍累计在 M01 的成本内；Typer 保持 V0。

## 覆盖与旧路线取舍

| 使用方式 | 任务 | 独立可结束的结果 |
| --- | --- | --- |
| 理解项目 | TY-U01 | 解释用途、关键流程与持久化边界 |
| 使用咨询 | TY-C01、TY-C02 | 可用接入方式；准确辨识已存在的类型能力 |
| 问题诊断 | TY-D01、TY-D02 | 无 BUG 的正确结论；在材料缺失时先澄清，再完成诊断 |
| 方案讨论 | TY-P01 | 与两个本地命令规模匹配、可行且有取舍的方案 |
| 工程修改 | TY-M01 | 用户应用新增导出并保留既有业务行为 |

旧路线 12 的“应用级类型适配注册”保留为将来的增强候选，本样板先评估用户是否根本不需要改库；旧路线 16 的跨命令位置是增强提案，D02 验的是当前选项归属与调用规则，不把提案倒写成原生 BUG。旧路线 17 的默认子命令与 D01 的单命令模式不同，不混为一项。

其余上游增强继续留在候选池，不强塞进这段商品接入业务。已有 Literal、自定义 parser、callback 和命令组不计新增工程改进；async 未自动等待也不在本样板中包装成缺陷。M01 是新应用需求，不冒称完成旧 20 项中的某项。

下一冻结阶段仍需物化各独立夹具、记录文件摘要、实跑正常与拒绝路径、校准条件披露材料和问答判据。本文没有新场景通过率、模型成本或 token 降低结论；这些应在真实投放后按任务类型与完整会话分别对账。
