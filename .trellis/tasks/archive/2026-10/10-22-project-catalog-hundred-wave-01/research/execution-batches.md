# 阶段内部执行清单

本阶段只对应一个Trellis任务。下列小批是制作与验证单位，不再创建子任务，全部30仓完成前本阶段不得关闭。

| 小批 | 项目 |
| --- | --- |
| 1.1 | cachetools、xmltodict、tabulate、python-decouple |
| 1.2 | click、cli-helpers、mistune、boltons |
| 1.3 | more-itertools、configobj、dataset、python-markdown |
| 1.4 | markdown-it-py、path、petl、toolz |
| 1.5 | jsonschema、docutils、agate、csvkit |
| 1.6 | python-box、rich、pydash、configargparse |
| 1.7 | backoff、bottle、deepdiff、cerberus |
| 1.8 | icecream、dpath |

小批先核实际源码，再冻结逐仓场景任务表与准入报告；每次原生、模拟及相关回归通过后保存证据。源码和离线依赖在阶段内可以分批落地，但不会把未准入项目先注册正式目录。
