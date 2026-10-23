# 候选审查：Colorama（未计入研究完成）

研究日期：2026-10-21。官方[tartley/colorama](https://github.com/tartley/colorama)，固定[841634ed2a0da5d5ac2d867db533da8131266cb2](https://github.com/tartley/colorama/tree/841634ed2a0da5d5ac2d867db533da8131266cb2)，版本0.4.7dev1；BSD-3-Clause，保留LICENSE.txt及版权/许可条件。已完成来源、真实源码、原生基线与实际使用核对。**当前有效目标不足20个，保留候选，不计入100项目完成数，不生成空路线补数。**

## 定位与规模

核心是在Windows控制台转换或透传ANSI，并按明确设置包装流。实际入口为just_fix_windows_console、init/deinit、AnsiToWin32与StreamWrapper；ansi模块提供最基本的Fore/Back/Style/Cursor常量，winterm/win32负责平台调用。本轮读取了这些真实类/方法及上游测试。跟踪49个文件、198,802字节；产品Python源码6文件、878行（排除colorama/tests）。必需运行依赖0，无服务/凭据。

[官方README](https://github.com/tartley/colorama/blob/841634ed2a0da5d5ac2d867db533da8131266cb2/README.rst)明确建议需要丰富样式的用户组合termcolor/Blessings/Rich，不接受新增ANSI生成类型的PR；旧init有已知重复包装问题，推荐使用just_fix_windows_console。因此不能把每种颜色/光标参数、样式常量生成、测试矩阵或文档分拆凑成20步。试点虽可维护分支，但目前只核实了少量独立转换/流行为问题，尚未形成完整20步。

## 实际验证与限制

独立venv安装原源码与unittest-xml-reporting，安装11.16秒、25,654,604字节（含报告工具，非运行包大小）。精确版本见requirements-frozen.txt。

在`ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`、UID/GID1000、无网络、只读根/源码/依赖、无账号HOME或凭据、删除capabilities、禁止提权、512MiB无额外swap、PID128的容器运行上游`unittest discover -p '*_test.py'`：**38通过、0失败/错误、14跳过**，测试进程0.272秒、RSS 26,656KiB。跳过原因原样统计：`{'sys.stdout is not a tty': 10, 'requires Windows': 4}`。真实Windows控制台、Win32调用、IDE终端和多Python矩阵均未验证；平台mock通过不能冒充Windows实机验证。

首次使用XMLTestRunner包装stdout，会破坏上游对sys.stdout身份的断言而失败1项。保留xmlrunner-attempt-*；之后换为原生TextTestRunner，执行结束后生成JUnit，未代理stdout，原版完整适用套件通过。没有修改上游来迎合测试工具。

真实场景使用AnsiToWin32(convert=False,strip=True)把带颜色的中文日志写入临时文件，重读仅得到“中文日志”，临时目录自动删除。另8条观察含1条通过对照：

- Linux仅strip处理OSC title仍调用winterm=None，抛AttributeError（与[上游#407](https://github.com/tartley/colorama/issues/407)对应）。
- 同一字符串含两个OSC时，先修改text再沿原字符串索引迭代，第二段控制序列残留且末尾正文丢失。
- 分两次write输入同一CSI会泄漏原序列；私有CSI和以ST终止的OSC不被当前正则剥离，属于协议扩展/流式处理的候选范围。
- writelines代理直接调用底层流，绕过write转换；write返回None，不保留普通TextIO.write字符数。这些需要决定兼容边界，不能一概称已确认违约BUG。
- 普通完整SGR正确剥离，为通过对照。

测试与观察容器均删除并核对不存在，无OOM。当前默认256MiB/PID64尚未实测；未实施上述修复、冻结增强验收或接入平台。

## 证据与重跑

证据根`.deploy/github-100-research/text-formats/colorama/`。source与venv独立保留；repository.json/revision.txt/size.json、issues.json、installation.json/installation-result.json/requirements-frozen.txt、baseline-output/tests.xml/process.log、baseline-result.json、reproduce.py/reproductions-result.json、observations-result.json与review-result.json均已保存。辅助脚本只生成报告，不改产品。

```bash
git clone https://github.com/tartley/colorama.git <checkout>
git -C <checkout> checkout --detach 841634ed2a0da5d5ac2d867db533da8131266cb2
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout> unittest-xml-reporting
```

在预备依赖的无网络隔离容器中，源码复制到临时目录并优先从该目录导入，运行`python3 /evidence/native_unittest.py`和`python3 /evidence/reproduce.py`；包装脚本中的原生发现模式与tox.ini一致。未提交、推送、部署、发上游消息或操作生产，也未执行平台模型评测。
