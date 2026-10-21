# CSVkit独立业务任务计划

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](csvkit-admission.json)为准。

固定`6d19c625214977ab2988e674441ca24638bc12d3`完整211文件及COPYING。已读CSVKitUtility构造／run／类型参数、CSVCut、CSVGrep、FilteringCSVReader、CSVSort、CSVSQL及真实project.scripts。当前镜像355主项为351通过／4上游Windows跳过，另31子项；依赖Agate1.14.2使用独立官方wheel，不用另一仓候选替代CSVkit实现。目标镜像en_US.UTF-8已实际探针验证，不安装系统locale或更改宿主。

四场景八项只读任务：引用CSV投影和投影后空行、匹配方式与多列筛选取证、排序类型和编号／空值保真、DDL预览与内存SQL查询。CV-D01缺真实命令及数据时不预判AND／OR或匹配方式；披露或不可用分支分别验收。正常／反例包括带逗号／换行单元格、短行、子串与精确匹配、多列ALL／ANY、数值与字典序、前导零和字面NA、DDL输出与仅末条查询结果。

所有文件均为合成临时CSV；SQL只在原生观察器的SQLite内存库执行固定查询，不连接外部数据库、不传真实连接串。咨询不执行导入、覆盖或生产SQL。工程目标0、requires为空，业务／协议／真实模拟／页面和完整交付分别留证。
