# 候选审查：ItsDangerous

**不计入研究完成数**。签名器核心边界较小；已实现密钥轮换、fallback signer、算法和序列化扩展、带时效校验、URL-safe压缩，尚未形成20个独立有效且不改变项目定位的交付。

官方来源：[pallets/itsdangerous](https://github.com/pallets/itsdangerous)，冻结 [672971d66a2ef9f85151e53283113f33d642dabd](https://github.com/pallets/itsdangerous/tree/672971d66a2ef9f85151e53283113f33d642dabd)，版本2.3.0.dev。已读LICENSE.txt，BSD-3-Clause，保留Pallets版权、再分发条件和免责声明。跟踪50文件／282547字节；已读Signer、TimestampSigner、Serializer、URLSafeSerializerMixin及异常接口。

独立临时检出、HOME、venv，Python3.12。核心无第三方运行依赖，测试使用pytest/freezegun，版本和安装报告冻结。完整原生 **297通过、0失败、0错误、0跳过**，1.06秒；安装8.36秒，环境51085916字节，包含测试工具。子进程RSS 75144 KiB为安装与测试共同观测最大值。未验证其他Python/OS矩阵、风格/类型或文档构建。

原生场景用合成密钥签含中文的URL-safe token；新旧密钥列表接受旧token、当前密钥生成新token、追加字节篡改被BadSignature拒绝。没有真实secret、账号或网络服务。现有常量时间比较、多密钥、fallback算法、自定义序列化、salt区分、时间戳/过期及自适应压缩不能重复列为新增。压缩输出预算、验签来源说明等可作为少量增强线索，但不把输入矩阵或算法参数拆满20步，也不把它扩成账号/令牌服务器。

证据：`.deploy/github-100-research/cli-config/itsdangerous/`。完整commit、元数据、原始原生日志/XML、依赖冻结、安装成本、observe.py与observations-result.json、review-result.json及SHA256摘要均保留。路线数0，尚未实施/冻结验收/接入正式库。

重跑：clone官方仓库、detached checkout上述commit，独立venv执行 `pip install -r <evidence>/test-requirements.txt -e <checkout>`；在checkout以隔离HOME、venv PATH执行 `<venv>/bin/python -m pytest -q -ra`，随后执行 `<venv>/bin/python <evidence>/observe.py`。未改上游源码、正式库或生产数据；未提交/推送/部署，未向上游发消息，平台评测模型调用为0。
