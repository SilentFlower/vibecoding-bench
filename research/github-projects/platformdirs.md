# 候选审查：platformdirs

状态：**原生基线已验证，暂不计入研究完成数**。当前尚未形成 20 个独立有效改进，建议该名额继续研究其他仓库，不能按路径别名拆步。

官方来源：[tox-dev/platformdirs](https://github.com/tox-dev/platformdirs)，固定 [6fe448ccf1837798f0adc3a577c61ee70c7d5c58](https://github.com/tox-dev/platformdirs/tree/6fe448ccf1837798f0adc3a577c61ee70c7d5c58)，MIT 许可，保留 LICENSE 和归属。纯 Python 平台目录定位工具，pyproject 要求 Python ≥ 3.11，无必需第三方运行服务。实际使用的是固定 commit 的浅检出，构建后元数据版本为 0.1.dev1+g6fe448ccf（浅检出 SCM 版本，不能当成官方发布版本）。

完整默认 pytest 实跑 **2266 通过、0 失败、125 跳过**，10.81 秒。跳过均保留在 baseline-tests.log，主要为其他操作系统／Android 的能力条件，本机 Linux 分支与上游模拟测试通过不等于 Windows/macOS 实机通过。安装本地源码、pytest、pytest-cov、pytest-mock、appdirs、covdefaults，20.12 秒，独立 venv 51973234 字节；无外部服务、账号或生产请求。没有运行文档、全类型／风格或全系统矩阵。

已读 api.py 的真实构造器与目录创建／place/find 实现、unix.py 的目录规则、__main__.py 和 pytest_plugin.py。原生场景在合成 HOME／XDG 环境中 place_config_file 写配置，再 find_config_file 找回实际内容；临时目录已清理，导入路径核对来自固定 checkout。

当前原版已有私有父目录创建、应用名／版本路径约束、根用户 site 目录策略、XDG 多路径、各类 find／place／iter 文件入口、pytest 环境隔离插件及大量用户媒体目录。它们都不能再作为本轮新增步骤。现有开放 #634 为 Windows HOME/USERPROFILE 场景、#629 为 illumos symlink-loop 场景，本轮未在对应原生系统复现，不冒充已确认缺陷。文档和测试维度不独立计数；尚不足 20 个合适交付时保留候选符合 SOP。

证据：`.deploy/github-100-research/cli-config/platformdirs/`。repository.json／issues.json 为官方信息，revision.txt 为完整提交；source-path.txt 指向隔离临时检出。installation.json／requirements-frozen.txt 记录安装；baseline-tests.log／xml／baseline-result.json 为原生结果；observe.py／observations-result.json 为写入／查找实测；review-result.json 明确 research_complete=false、roadmap_steps=0。

重跑：clone 官方仓库并 detached checkout 上述完整 commit，独立 venv 安装 `<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>`，在临时检出执行 `<venv>/bin/python -m pytest -q -ra`，再运行 observe.py。依赖准备可联网，原生使用场景不需要网络。

未实施功能或独立冻结验收，未接入平台，不修改正式库、上游源码或生产数据，未提交／推送／部署或发上游消息。
