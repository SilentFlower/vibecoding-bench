# 剩余九十项目的三阶段接入计划

用户反馈二十三个子任务过多，改为一个总任务和三个阶段子任务。每阶段固定三十个项目，内部按少量项目分批制作与验收，不为小批再建任务。初始为10项目／45场景／107任务；三阶段已交付，当前v37-en实际100项目／426场景／726任务。母任务正在补最终集成审查，阶段本地完成与Close人审状态分列。

| 阶段 | 项目全集 | 本阶段新增 | 全前序阶段都通过后的累计目标 |
| --- | --- | ---: | ---: |
| 1 | cachetools、xmltodict、tabulate、python-decouple、click、cli-helpers、mistune、boltons、more-itertools、configobj、dataset、python-markdown、markdown-it-py、path、petl、toolz、jsonschema、docutils、agate、csvkit、python-box、rich、pydash、configargparse、backoff、bottle、deepdiff、cerberus、icecream、dpath | 30 | 40 |
| 2 | alive-progress、jmespath、confuse、simplejson、marshmallow、inflect、tqdm、pyyaml、pluggy、xlsxwriter、mistletoe、python-docx、python-pptx、mdit-py-plugins、dynaconf、attrs、cssselect、structlog、cattrs、flask、babel、anytree、werkzeug、html2text、packaging、bibtexparser、treelib、sqlparse、python-dateutil、ftfy | 30 | 70 |
| 3 | pypika、arrow、charset-normalizer、injector、loguru、pyparsing、markdownify、pyrsistent、feedgen、sortedcontainers、wtforms、python-constraint、feedparser、portion、textdistance、humanize、bidict、tablib、chardet、natsort、transitions、html5lib、pendulum、python-liquid、python-statemachine、webcolors、wrapt、funcy、collective-icalendar、sqlglot | 30 | 100 |

## 队列与完成边界

auto-loop显式队列为三个阶段子任务和最后的母任务整体集成，共四项。母任务通过显式depends-on依赖三个阶段；三个阶段不因列表先后自动产生依赖，均在实际当前已准入目录上追加，实际可执行共享适配按证据处理。

所有九十仓必须完成，受阻项仍留待办。每阶段内部清单及来源在对应任务research目录，研究状态、原生、模拟、真实模型、本地提交和生产状态分别记录。旧十项目数量深化目标继续由原母任务管理。

不承诺固定日历日期，不把每仓二十项当配额；全量接入后如实报告既有约600～800场景／2000独立任务方向的覆盖及数量差距。

## 当前本地交付对账

| 阶段 | 新增项目 | 新增场景 | 新增独立任务 | 其中修改 | 已完成本地提交 |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 30 | 126 | 244 | 9 | `ada3ff9053d81dda478046571781dcd9de91ec9e` |
| 2 | 30 | 134 | 192 | 8 | `6ca422ab76eb967381b508602246924234065953` |
| 3 | 30 | 121 | 183 | 3 | `d246f393886538a295d340c0b30ec0c5f1d9b760` |
| 本轮新增 | 90 | 381 | 619 | 20 | 三阶段均已完成全量检查及本地提交 |
| 含原十项目的正式全集 | 100 | 426 | 726 | 37 | v37-en，母任务最终本地交付按runner续行 |

九十仓完整适用原生主项210536：通过201302、跳过7413、预期失败1820、SQLParse原版非严格XPASS一项；失败／错误／未执行均零。子项47666另列，不叠加主项。642条业务及正反候选路径全部符合独立期望。

45批真实产品链mock共1781路径，其中18条是既有Arrow控制回放；1763条新增任务路径覆盖619个唯一新增任务，不能按路径膨胀任务数。独立代码接受49次对应20个新增修改目标；页面28552项检查、1454张截图。80条材料不足路径和151次披露交付单列，模拟回答／评审／用量不代表真实模型效果。

最终32188文件与Git沿生产恢复函数导出及Docker COPY相等；原始Git autocrlf导出的两份Dateutil CRLF差异仍记录为false。原十项目3069份旧文件及二百份历史报告／路线逐项未变，265个无关dirty文件保持。完整百项目API和新建暂停批次对账为100实例／426场景／726任务，默认入口选择726项；候选、评审及验收零执行。无当前目录、无旧缓存的新reader仍能重读全部100个历史实例及冻结release；合成数据副本已清理。

SQLGlot按用户“可以拿继续”的明确确认保留固定公开主仓 `67961afbed7c986dfe26ab82db89a25814c1bdcb`，公开全部1500主项／21780子项通过。私有可选集成测试子模块 `8cbf013a7b0bd1871abce4ebb543560d0e554799` 未获取、未验证，不计通过，公开加载器与测试不删减。

当前离600场景还差174，离800场景还差374，离2000独立任务还差1274；本轮固定九十仓全部接入已达成，后续数量深化仍是独立工作。真实模型／OAuth均未调用，未push或部署。三阶段本地完成的Close均保留 `decision-review-required`，具体摘要见 `final-integration-audit.json`，不由AI代签人工复核。
