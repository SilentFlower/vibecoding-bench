# 阶段内部执行清单

本阶段只对应一个Trellis任务。下列小批是制作与验证单位，不再创建子任务，全部30仓完成前本阶段不得关闭。

| 小批 | 项目 |
| --- | --- |
| 2.1 | alive-progress、jmespath、confuse、simplejson |
| 2.2 | marshmallow、inflect、tqdm、pyyaml |
| 2.3 | pluggy、xlsxwriter、mistletoe、python-docx |
| 2.4 | python-pptx、mdit-py-plugins、dynaconf、attrs |
| 2.5 | cssselect、structlog、cattrs、flask |
| 2.6 | babel、anytree、werkzeug、html2text |
| 2.7 | packaging、bibtexparser、treelib、sqlparse |
| 2.8 | python-dateutil、ftfy |

小批先核实际源码，再冻结逐仓场景任务表与准入报告；每次原生、模拟及相关回归通过后保存证据。源码和离线依赖在阶段内可以分批落地，但不会把未准入项目先注册正式目录。
