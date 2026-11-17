# 技术设计

## 处理链与边界

controller为模板/恢复操作跟踪固定阶段，在原finally删除目录之前调用失败诊断模块。supervisor为挂载、PID准备、CRIU执行、执行体/熵校验及报告阶段建立同样的受控上下文，失败时先在当前root私有实例目录写有界内部摘要，再沿原退出路径结束。控制器清理前安全读取副摘要，保留首个上游失败并注明后续报告解析异常。

新增native/criu/diagnostics.py作为白名单编码、日志提取和私有摘要写入的唯一实现。固定schema_version=1记录operation/stage/exception_type/errno/reason、模板/worker/实例UUID、criu_returncode/process_returncode、受限源码位置、log_status/log_evidence及upstream_status/upstream。阶段、操作与标准异常名称使用受控集合；errno/退出码严格检查类型及范围；标识仅接受规范UUID。CRIU日志只读取固定当前实例/模板目录下的有限尾部，提取受限源码模块/行号及固定错误分类。错误/警告分别保留，固定日志尾部读取上限16KiB、证据最多8项。真实CRIU4.2的protobuf.c:72 Unexpected EOF映射为unexpected_eof分类。未知内容记unknown，不复制异常str、traceback正文或任意路径。

失败持久目录为/var/lib/ccrb-criu/failures，复用原root私有持久挂载。最多32份、每份8KiB。仅在失败路径落盘，目录0700、文件0600，采用独立UUID文件名与安全排他发布。轮换核对常规文件、单链接、root归属及受控命名；外来或不安全内容拒绝操作。诊断失败仅发固定诊断故障码，原异常继续传播，原资源清理继续执行。

## 保持的合同

控制器现有reason及IPC消息继续沿原合同，新诊断事件独立输出结构化白名单字段。正常取消沿原取消清理；重建模板/恢复及普通exec回退沿现有单调截止，任何日志失败均不得新增模型发送或资源释放捷径。

supervisor只负责本实例的内部副摘要；controller负责清理前聚合和全局有界留存，避免清理后丢失原始阶段。成功路径维持原CRIU、共享inode、降权和熵核验流程，避免增加私有日志扫描或业务等待。

## 分发与验证

export_bundle.py与package.py显式包含新增模块，并更新images/v3/criu及source-manifest。CRIU二进制、补丁和运行时分发摘要保持原版本。故障注入使用合成标识和凭据，结合真实文件/FD验证清理；独立子进程覆盖supervisor失败到controller空报告的首错汇总。复用已有隔离KVM夹具验证成功恢复与失败回退的边界，避免真实账号或付费调用。

## 计时解释

线上1855ms来自start_spare后台任务总耗时，包含失败恢复与普通exec回退。当前有空闲worker时业务checkout直接返回，现场前27笔checkout均为0ms。无空闲且spare存在时请求等待其ready，等待包含在checkout和prepared中；后台CPU占用还可能产生资源竞争，不能将后台耗时解释为全场景零影响。
