# 阶段内部执行清单

本阶段只对应一个Trellis任务。下列小批是制作与验证单位，不再创建子任务，全部30仓完成前本阶段不得关闭。

| 小批 | 项目 |
| --- | --- |
| 3.1 | pypika、arrow、charset-normalizer、injector |
| 3.2 | loguru、pyparsing、markdownify、pyrsistent |
| 3.3 | feedgen、sortedcontainers、wtforms、python-constraint |
| 3.4 | feedparser、portion、textdistance、humanize |
| 3.5 | bidict、tablib、chardet、natsort |
| 3.6 | transitions、html5lib、pendulum、python-liquid |
| 3.7 | python-statemachine、webcolors、wrapt、funcy |
| 3.8 | collective-icalendar、sqlglot |

小批先核实际源码，再冻结逐仓场景任务表与准入报告；每次原生、模拟及相关回归通过后保存证据。源码和离线依赖在阶段内可以分批落地，但不会把未准入项目先注册正式目录。
