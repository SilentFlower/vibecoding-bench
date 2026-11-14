# 技术设计

## 工作结构与共享入口

父任务负责跨子项的共用app.js/main.py/部署接线和最终集成检查。子任务按原生池、嵌入导航、账号门禁展示、CLI遥测四个责任单元维护证据。父任务具有直接集成实现工作。

## 导航

Environments.vue区分外层environments与tasks文档视图；tasks缺省内层accounts。accounts为默认地址，显式tasks子页保留tab=tasks。iframe生命周期绑定文档视图，同一文档的二级导航使用受控hash替换和现有runtime:navigate消息同步顶层历史，避免完整source变化销毁iframe。刷新以顶层URL恢复，后退前进只恢复一次。内层异步渲染按viewGeneration和当前Tab丢弃迟到结果。

## 账号门禁

现有QuotaGuard按稳定账号身份保存account_error，令牌轮换与普通成功响应均不能自行清空。11-5当前任务记录含invalid_grant，网关账号active且auth_error为空；这两类事实来自不同状态源。保留后台授权与额度门禁，账号卡片明确已有认证异常记录与“额度”核验路径。复用POST /api/accounts/{id}/quota的原owner锁、绑定复核、凭据同步和record_manual_usage流程。核验完成重新读取账号卡片的passive_quota，防止后台已解除而页面仍保留旧提示。tab/账号变化后迟到结果不写入新页面。当前生产数据保持只读。

## CLI遥测

提供V3_CLI_TELEMETRY=off|on，缺省及空值归off，非法值拒绝。共享策略函数投影官方DISABLE_TELEMETRY、DISABLE_ERROR_REPORTING关闭键；off输出1，on从受控CLI settings及最终进程环境移除关闭键，避免0仍被解释为禁用。独立DISABLE_AUTOUPDATER=1继续保留。部署compose与example.env把选项传至orchestrator；普通任务、项目/Pi、养号及交互CLI沿共用准备入口应用。官方CLI分发及原生发送栈遥测策略各自保持所有权。新策略纯函数模块随现有orchestrator镜像复制进入制品，宿主固定源码的新增直接依赖按来源清单核对。

## 原生池

NativePool默认idle_timeout改为300秒，保留现有弱引用回收循环。现有真实子进程回归覆盖空闲120秒时仍为2个、301秒时仅1个及实际退出后许可归零。验收脚本N4等待315秒；历史内存测量明确标为既有数据。

## 验证与恢复

浏览器使用实际构建页面、合成API和独立profile；断言iframe元素与文档身份、默认账号、全部二级Tab、定位参数、刷新及历史恢复、迟到响应和桌面/移动端。后端覆盖手动核验成功/失败与真实门禁、默认/显式/非法遥测配置、各入口实际执行环境。网关886项回归证据保留首次连接重置及成功补跑。部署变量变更、正式发布和生产安装由后续具体授权进入；本批不直接改生产数据库或启动模型测试。
