# WTForms：真实 GitHub 项目研究

研究完成：来源许可、固定真实源码、完整适用原生基线和普通商品表单业务场景已核对，形成[20项独立交付及验收边界](./wtforms-roadmap-20.md)。**仅研究，未实施路线、未冻结独立验收、未接入正式库。**

## 来源许可与代码规模

官方仓库[pallets-eco/wtforms](https://github.com/pallets-eco/wtforms)，固定完整提交[`af18fd6a7595d374aa707ff97b73df0dcc462ec2`](https://github.com/pallets-eco/wtforms/tree/af18fd6a7595d374aa707ff97b73df0dcc462ec2)，源码版本3.3.0b3；提交2026-10-20。实际从官方clone后detached checkout，与repository.json/commit.json/revision.txt一致。旧cli-config中的临时源码已不存在，所以在resume-app建立新固定检出，没有把旧临时路径当可重跑源码。

已读LICENSE.rst，BSD-3-Clause，保留WTForms版权、三项再分发条件与免责声明。跟踪**153文件、737,860字节**，84个Python文件合计**11,612行**（含测试工具）。已读取Form/BaseForm/FormMeta、Field处理/校验链、FormField/FieldList、SelectChoice/Choice/动态工厂、数字字段、Optional/NumberRange等规则、DefaultMeta、widget渲染和相关原生测试。字段和入口按该提交定义核对，未改写为简化工程。

## 独立环境与完整原生基线

本机独立source/venv/isolated-home根`.deploy/github-100-research/resume-app/wtforms/`，宿主Python**3.12.3**、Linux x86_64。安装本地editable源码、pytest9.1.1、Babel2.18.0、email-validator2.3.0、WebOb1.8.11等实际测试依赖，耗时**15.477秒**，环境**86,055,758字节**。上游运行依赖MarkupSafe，邮件/区域/WebOb为本轮完整测试覆盖成本；精确冻结见requirements-frozen.txt。

完整原生pytest **537通过、0失败、0错误、0跳过、0 xfail/xpass**，耗时**1.439秒**，峰值RSS **50,984KiB**。原始CLI摘要与JUnit一致。**唯一警告过滤**为WebOb在Python3.12导入cgi触发的`DeprecationWarning`消息前缀`'cgi' is deprecated`；其余上游warnings=error保持。旧cli-config/wtforms/baseline-tests.log的收集失败原样保留，本轮明确是依赖兼容警告处理，不算WTForms缺陷，也未修改原生测试。其他Python/OS、文档和静态类型检查未跑；该过滤不能证明Python3.13兼容。

所有观察均不需要Web服务器、数据库、账号或外部业务调用。原生商品Form成功把中文名称和库存字符串3转换成业务数据并populate_obj到合成对象；非法整数/空名产生实际字段错误；widget输出真实控件HTML。

## 逐项发现与现有能力排除

observe.py从固定source/src/wtforms导入，20个观察键封存在observations-result.json。唯一修复提案是额外filter/validator列表所有权：共享空列表经两次构造/验证变长2，导致内联规则留在调用者列表并重复运行；process和validate同根症状归一个交付，不拆两步。

其他19项均明确为增强：来源感知Optional、async链、双向展示转换、输入来源、部分验证、嵌套JSON提交适配、动态Form派生、结构化问题、跨字段规则、验证过程诊断、流式批量验证、对象填充预览、辅助说明/错误关联渲染、disabled选择业务策略、业务键列表、逐项组合规则、首错停止、显式字段顺序和机器可读字段说明。原Optional的raw_data规则、populate_obj顺序写入、Form禁止实例加字段等既有约定不冒充BUG。

最新源码已经有接收(form,field)的choices回调与post_process、有enum helper、disabled HTML呈现、FieldList插入/弹出/重编号及obj/data回退；均实际读取并排除。disabled选择提案只新增明确的可选性验证策略，不把已有disabled渲染当缺失。schema提案是字段说明清单，不宣称生成完整JSON Schema。每项包含正常/边界验收、真实模块与原生回归、兼容和实际依赖，没有实施或冻结验收通过的宣称。

## 证据与重跑

证据根包含官方元数据/issue线索、commit/revision、安装日志/冻结依赖、size.json、baseline-result/log/XML/time、observe.py与observations-result/log、roadmap-20.json、review-result.json和evidence-sha256.json。旧临时证据保持不改，最新报告使用resume-app实际导入路径。

项目根重跑普通业务场景：

```bash
PYTHONDONTWRITEBYTECODE=1 .deploy/github-100-research/resume-app/wtforms/venv/bin/python .deploy/github-100-research/resume-app/wtforms/observe.py
```

完整基线在source目录，以独立venv执行`python -m pytest -q -ra -p no:cacheprovider --junitxml=<证据目录>/baseline-tests.xml -W "ignore:'cgi' is deprecated:DeprecationWarning"`，设置证据目录内隔离HOME与venv PATH；完整当轮命令见baseline-result.json。异机先clone官方URL并detached checkout固定commit，按requirements-frozen.txt重建venv，将editable项替换为本地源码，核对导入路径后再测。首次安装需依赖源，未来冻结验收仍需离线wheelhouse；本机路径不是跨机器可用性保证。

上游源码git干净，未改正式库、产品代码或真实对象/数据库，未实施路线、提交、推送、部署或向上游发消息。
