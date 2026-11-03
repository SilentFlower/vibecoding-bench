# 工程迭代导航验证

## 实际执行

- `node --check webui/app.js`、`node --check webui/projects.js`、Python 验证器编译及 `git diff --check` 通过。
- `PYTHONUNBUFFERED=1 PATH="$PWD/.deploy/v3-ownership-implementation/bin:$PATH" .venv/bin/python deploy/v3/verify_stack.py --manifest .deploy/v3-ownership-implementation/release-a6.json --source-overlay --browser --project-iteration` 最终退出 0；只读覆盖摘要 6bbc92f4cfbb55eb8d819bb2432d5d388843f1aa80a92a8aaaeaa1c8b290a2e9。
- 使用 Chrome/CDP、实际网关 Cookie、真实 Projects/Warmup HTTP、SQLite 和 SSE。两个合成账号、两个空间各自配置、12 条工作及25条交互、终端观察均保存在隔离数据库；没有模型或第三方 OAuth 调用。
- 两次完整通过：最终版增加等待新 Document，确保刷新检查不误读旧 DOM；此前已修正测试事件构造语法及网络盘点遇已删除网络的时序问题。
- 本轮 Check-All full：三件套映射、API/组件/历史/跨层假设、规范与验证均通过；没有剩余 CHK/FBK。

## UA1–UA6

| AC | 证据 |
| --- | --- |
| UA1 | 仅一个工程顶层入口，两个页内链接；实际 Enter 键激活、aria-current 与顶层选中正确 |
| UA2 | A/B 选择、跨空间切换、实际刷新、新 Document、前进/后退保持账号；非法、超安全范围、重复、已停用及软删除账号均提示且不默认其他账号 |
| UA3 | 两空间不同项目池、指南、计划、终端和历史分页正确；导航阶段仅 GET，全部持久业务表前后逐值一致，未保存输入不落库 |
| UA4 | #projects/#warmup 旧链接默认选择有效，账号页 Pi 入口直达带账号 URL；地址是唯一持久来源 |
| UA5 | 真实旧快照响应延迟后切空间，旧响应不覆盖新 DOM；连续20次切换，最多1个SSE、时钟不累积，离开页面全部释放 |
| UA6 | 两边终端/记录分页/CLI设置/抓包窗口路径正确，切空间关闭旧窗口；显式设置只写相应开关；1280/720/390px 明暗主题无横向溢出，截图实际检查通过 |

## 限制与后续

- 工作/计划/历史保持通过真实数据库事实和无业务写入证明；没有把合成持久状态称为实际模型正在执行。后台调度与执行代码未修改，复用 A 的完整后端回归。
- 正式镜像来自后续干净 CI。父任务补交叉维护状态场景并部署 US，生产只读验收，不中断工作。
- 原保留348文件SHA256不变；A的归属状态和恢复入口保留。
