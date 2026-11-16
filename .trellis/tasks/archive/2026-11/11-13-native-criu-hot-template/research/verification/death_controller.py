"""以独立真实进程持有产品控制器，供强退测试。"""
import asyncio,socket,sys
sys.path.insert(0,'/opt/ccrb-criu')
from controller import Controller
async def main():
    """在一次性客体运行合成验收。@return 合成验证结果或无。"""
    listener=socket.socket(fileno=int(sys.argv[2]));listener.setblocking(False)
    service=Controller(int(sys.argv[1]),8,'/probe/native',{'image_sha256':'564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79','image_bytes':112843960})
    print('READY',flush=True)
    await service.serve(listener)
asyncio.run(main())
