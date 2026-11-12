# Typer：真实 GitHub 项目研究

官方来源、许可、固定源码、完整适用原生集合及本地商品命令已核对，形成[20项CLI增强路线](./typer-roadmap-20.md)。**仅研究，未实施路线，未冻结新增验收，未接入正式库。**

## 来源、许可与规模

官方当前仓库 [fastapi/typer](https://github.com/fastapi/typer)，完整commit `a5882dedf0bc7a46cd861fdfca020f88519e0f21`，版本0.27.3；官方GitHub元数据与pyproject仓库URL一致，未沿用旧组织名。主[LICENSE](https://github.com/fastapi/typer/blob/a5882dedf0bc7a46cd861fdfca020f88519e0f21/LICENSE)为MIT，保留Sebastián Ramírez版权。内置typer/_click/LICENSE.txt为Pallets的BSD三条款，逐条读并保留；_typing.py原Pydantic来源说明保留。当前版本vendored Click，不冒称依赖外部click发行包。

真实读取Typer/CommandInfo/ParameterInfo、参数注解转换、callback包装、group命令合并、CliRunner执行/返回与vendored Context来源/资源接口，核对Rich/子命令解析相关实现和真实tests。跟踪776文件/2084485字节；638个Python文件/35749行。独立venv55754642字节，安装11.947秒，实际版本/制品SHA见requirements-frozen.txt和installation.json。

## 实际原生与业务验证

按上游scripts/test.sh完整测试配置执行，保留coverage及strict warnings/xfail，completion安装用例显式启用；只把auto进程数限定2，独立HOME/XDG目录。**1481主项通过、22普通skip、2xfail、0xpass、退出0**；181.272秒，最大RSS101480KiB。宿主Python3.12.3真实运行，不冒称镜像Python3.12.15结果。原生当轮JUnit/log/time/result及完整环境保留，skip/xfail原例逐项在baseline-result.json；未删改测试或屏蔽pytest集合。

22项普通skip为20个Windows、2个macOS平台条件；2项xfail是tests/test_rich_markup_mode.py的Markdown列表单/双换行原标记，分别test_markup_mode_bullets_single_newline与test_markup_mode_bullets_double_newline的markdown-lines0参数。没有把这些预期失败列为已修，也未将其列入本次20项增强的修复目标。

旧cli-config/typer原测试日志中途未完成，没有成功baseline-result，未复用为通过；本轮检出恢复到同commit、安装新venv并运行完整集合。若以后复跑，runner检查已有result/XML会拒绝覆盖，须显式归档旧证据后再运行。

实际中文商品命令咖啡 --quantity 3返回0/stdout咖啡:3，非法quantity返回2和真实stderr。20项原版观察已封存observations-result.json，包含原构建异常、async未被等待的返回、实际覆盖/参数位置规则和已有能力对照。async观察显式close未等待协程，未将exit0当异步业务已完成。

## 路线真实性

20条全部为增强：async、时间/金额/Union/记录/映射/成组参数、关系规则、本地配置、manifest/lazy/适配注册/依赖、结构化错误/语言、全局选项位置/默认命令/规范别名/碰撞策略及typed argv构造。每项有独立业务交付、真实模块、正常/边界验收、原生回归与实际依赖。

Literal已在源码和控制场景实际通过，未列新增；datetime、Optional/list/tuple、custom parser/click_type、Context.with_resource/default_map等既有能力亦排除。Decimal等提案包含约束/help/格式元数据而非仅包装一个parser；同函数重复注册别名已可行，提案限定规范别名metadata与一致路由。默认覆盖与位置规则不叫BUG。新API名是拟议契约，完整原版通过不证明新路线通过。

## 证据与重跑

证据根.deploy/github-100-research/resume-app/typer包含官方仓库/issue、固定revision/源码、安装报告/冻结依赖、原生log/JUnit/time/result、20观察、20步JSON、review及SHA清单。项目根重跑本地业务：

```bash
PYTHONDONTWRITEBYTECODE=1 .deploy/github-100-research/resume-app/typer/venv/bin/python .deploy/github-100-research/resume-app/typer/observe.py
```

完整基线原命令/环境见baseline-result.json与run_native_local.py。跨机器先检出官方同commit，按冻结依赖重建venv并核对真实import，使用隔离HOME/XDG与同上游测试环境参数；本地路径不是可移植交付保证。未来冻结阶段仍需离线制品准备。tracked源码干净，未改正式库、实施路线、提交推送部署或发上游消息。
