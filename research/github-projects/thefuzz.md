# TheFuzz 候选：基线通过，未满足二十步准入

官方 [seatgeek/thefuzz](https://github.com/seatgeek/thefuzz)，固定 `1ba86f33a19deedcf886b74cf6efffd79495a50f`。实际LICENSE.txt为MIT，署名SeatGeek；Python>=3.8，运行依赖RapidFuzz>=3,<4。23个跟踪文件、567872字节，Python产品626行。setup.py URL与官方网页/固定git一致，REST403限流证据保留，不使用宿主token。

读取fuzz.py、process.py与utils.py：八种核心评分器直接转发RapidFuzz；process提取/排序也调用rapidfuzz.process，主要保留旧API的预处理、取整和dict/list返回结构。它是实际兼容封装项目，不等于该仓拥有RapidFuzz的底层算法。

上游tox相同pytest完整集合在无网络、无账号目录、只读源码与根、UID1000、256MiB/PID64的V3容器 **71通过、0失败/错误/跳过**，2.777秒。准备了上游对应Hypothesis/pycodestyle；不把Hypothesis生成示例次数当新测试项。真实候选服务名称模糊匹配及键保留场景通过，match.json写出后由标准json独立读回。

暂不计入100：未形成20条由此固定工程独立承载的用户行为迭代，评分器/测试组合不可重复凑数，底层RapidFuzz算法也不可冒称在此仓实现。保留可用小基准候选；若未来确有20条具体封装层需求，应先重新审查再形成路线。

证据根 `.deploy/github-100-research/data-tools/thefuzz/` 保存来源、固定依赖、原生JUnit/log、smoke.py/JSON文件与review-result.json。可复跑 `research_runner.py --name baseline run thefuzz -- /usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider --junitxml=/output/baseline-tests.xml`；业务入口同runner执行 `/usr/local/bin/python3 /smoke.py`。未实施功能、正式接入或部署。
