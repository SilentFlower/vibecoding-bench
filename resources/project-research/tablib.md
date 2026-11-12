# Tablib：真实 GitHub 项目研究

来源许可、固定源码、适用完整原生集合和实际本地商品导入导出已核对，形成[20项独立路线](./tablib-roadmap-20.md)。**仅研究，未实施路线，未冻结新增验收，未接入正式库。**

## 来源、许可与规模

官方 [jazzband/tablib](https://github.com/jazzband/tablib)，完整commit `966876c76a6378557c1951badc1665b4d1375875`。主仓[LICENSE](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/LICENSE)为MIT，保留Kenneth Reitz/Jazzband版权。内嵌_vendor/dbfpy的官方SourceForge主页和PyPI均声明Public Domain，保留Jeff Kunce等原作者历史归属；见official-source-verification.json，未用主仓MIT替代第三方声明。

真实读取完整Dataset/Row/Databook、format registry及CSV/JSON/YAML/XLSX/HTML/DataFrame/SQL实现，核对XLS单元导入导出和ODS格式入口，关联原生tests。跟踪77文件、367729字节；33个Python文件共7038行。独立环境197477603字节，安装37.666秒；包含全部格式依赖和pandas，实际版本见requirements-frozen.txt，安装制品/hash见installation.json。

## 完整原生基线与实际场景

复用已经通过的上游tox默认tests集合，未重跑长基线，pytest.ini的coverage配置保留，全部格式依赖和pandas均安装：**183主测试通过、0普通skip、0xfail、0xpass、退出0**，7.047秒，最大RSS123224KiB；512MiB离线只读容器，临时可写源码副本，无原检出修改。测试镜像实际Python3.12.15已另以同镜像读取sys.version核实，安装与本地观察使用宿主Python3.12.3，二者不混写。这里没有另行宣称tox docs/lint或完整解释器矩阵通过。

首次研究runner未加入src路径而收集失败，证据保留runner-layout-first；修正研究夹具后原tests完整通过，产品代码未改。当轮JUnit/log均存在；未用旧XML顶替新结果。

observe.py实际调用固定检出：中文商品CSV往返，明确CSV数量仍str；XLSX往返保持整数与中文，双sheet工作簿真实导入size=2。20条原版观察逐项保存observations-result.json。字典键错位和首列动态列错位均真实复现；其他新增能力标增强，未把完整原版通过说成新契约已通过。

## 路线与兼容

2项修复针对真实行列对应错误；18项增强覆盖显式重置/原子导入、有界记录流与输出、缺失值/类型规则、切片排序去重、关联聚合透视、电子表格选区/样式/标识符精度、HTML、本地文件和工作簿管理。每项含正常/边界验收、真实源码模块、关联原生回归与实际依赖，均可独立交付。

已有CSV export_stream_set返回已全量填充的StringIO，因此新增只提按需分块，未声称没有file-like输出。已有动态列/formatter/transpose/按行去重/位置stack等也不当新增。长标识符样本568883383628111873在XLS/XLSX中因数值存储精度失真，提显式text/warn/error策略，未声称可改变电子表格数值精度；旧issue的568883383628111872在当前环境可精确往返，未误列为已复现BUG。

## 证据与重跑

证据根.deploy/github-100-research/resume-main/tablib包括来源元数据/许可核查/固定revision、安装和冻结依赖、原生JUnit/log/result、初轮失败、运行时版本、20观察、20步JSON、review与SHA清单。项目根可重跑业务观察：

```bash
PYTHONDONTWRITEBYTECODE=1 .deploy/github-100-research/resume-main/tablib/venv/bin/python .deploy/github-100-research/resume-main/tablib/observe.py
```

跨机器先clone官方URL、detached checkout同commit，按冻结制品重建环境，核对导入路径；本机绝对路径不等于可移植交付。run_native.py保留原实际基线命令，但今后复跑必须先归档原log/XML/result，清理当轮XML后运行，失败不得读取旧JUnit。未来冻结阶段还需离线依赖制品封存。tracked源码干净；未修改正式库、实施路线、提交推送部署或发上游消息。
