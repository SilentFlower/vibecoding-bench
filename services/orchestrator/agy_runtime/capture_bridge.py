"""按真实CLI初始化事件建立原生就绪。"""
import time
from . import native_bridge as rpc_runtime

class ResearchBridge(rpc_runtime.NativeBridge):
    """在原生固定桥接流程中选择独立研究观察器。"""

    def __init__(self, folder, backend, reclaim, sink):
        """初始化固定观察后端。@param folder 私有目录。@param backend 研究后端。@param reclaim 冷页。@param sink 事件诊断。@return 无返回值。"""
        super().__init__(folder,reclaim,event_sink=sink)
        self.research_backend=backend

    def _start(self):
        """只在启动期间切换观察器资产根。@return 无返回值。"""
        self.cli_begin=len(self.cli_events)
        return super()._start()


    def _pump(self, wait=0.05):
        """使用固定原版真实init事件建立候选后端就绪。@param wait 等待秒数。@return 无返回值。"""
        super()._pump(wait)
        if not self.research_backend.startswith('candidate') or self.native_ready:return
        for event in self.cli_events[getattr(self,'cli_begin',0):]:
            if event.get('event')!='init':continue
            if event.get('init',{}).get('cwd')!=str(self.run_folder):raise RuntimeError('原生init工作目录归属冲突')
            if not self.native_pid:raise RuntimeError('原生init缺少执行体观察握手')
            ready={'event':'native_ready','generation':self.generation,'native_pid':self.native_pid,
                'source':'native_cli_init','conversation_id':event['conversation_id'],'cwd':event['init']['cwd'],'ns':time.monotonic_ns()}
            self.native_ready=True;self.native_events.append(ready);self._emit(ready)
            return
