"""固定官方映像的只读Clearcut队列观测，候选对象来自本次子进程。"""
from .validation import require
import hashlib
import os
from pathlib import Path
import struct
import time

SHA='39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'


class QueueReader:
    """按已核对的原生布局读取活跃Clearcut候选对象。"""

    def __init__(self, bridge):
        """绑定本代执行体。@param bridge 本实验工作进程。@return 无返回值。"""
        self.bridge=bridge;self.pid=bridge.native_pid;self.generation=bridge.generation
        binary=Path(f'/proc/{self.pid}/exe');image_info=binary.stat();digest=hashlib.sha256()
        with binary.open('rb') as stream:
            for block in iter(lambda:stream.read(1048576),b''):digest.update(block)
        require(digest.hexdigest()==SHA)
        require(int(Path(f'/proc/{self.pid}/status').read_text().split('PPid:')[1].split()[0])==bridge.proc.pid)
        self.fd=os.open(f'/proc/{self.pid}/mem',os.O_RDONLY);self.clients=set();self.scan_bytes=0
        self.maps=[];self.base=None
        for row in Path(f'/proc/{self.pid}/maps').read_text().splitlines():
            columns=row.split();lo,hi=[int(v,16) for v in columns[0].split('-')]
            self.maps.append((lo,hi,columns[1]))
            # sealed memfd通过真实exe句柄读取，VMA身份由设备及inode核对。
            major,minor=(int(value,16) for value in columns[3].split(':'))
            if os.makedev(major,minor)==image_info.st_dev and int(columns[4])==image_info.st_ino:
                if 'w' in columns[1] and columns[1].endswith('s'):raise ValueError('映像存在可写共享映射')
                if columns[2]=='00000000':self.base=lo
        require(self.base is not None)

    def read(self, address, size):
        """读取指定范围。@param address 本进程地址。@param size 字节数。@return 原始字节。"""
        data=os.pread(self.fd,size,address)
        if len(data)!=size:raise ValueError('原生字段读取不足')
        return data

    def discover(self):
        """用真实接口表找到队列候选，限制每次扫描缓冲。@return 本代候选地址数。"""
        marker=struct.pack('<Q',self.base+0xcb6de70)
        for row in Path(f'/proc/{self.pid}/maps').read_text().splitlines():
            cols=row.split();lo,hi=[int(v,16) for v in cols[0].split('-')]
            if cols[1][:2]!='rw' or len(cols)>5 and cols[-1] not in ['[heap]','[stack]']:continue
            for start in range(lo,hi,262144):
                try:blob=self.read(start,min(262144,hi-start))
                except (OSError,ValueError):continue
                self.scan_bytes+=len(blob);at=blob.find(marker)
                while at>=0:
                    if (start+at)%8==0:
                        try:
                            logger=struct.unpack('<Q',self.read(start+at+8,8))[0]
                            client=struct.unpack('<Q',self.read(logger,8))[0]
                            item=self.state(client)
                            if item['source'] in [2747,2992,327]:
                                self.clients.add(client)
                                metalogger=struct.unpack('<Q',self.read(client+240,8))[0]
                                if metalogger:
                                    internal=struct.unpack('<Q',self.read(metalogger+144,8))[0]
                                    if self.state(internal)['source']==2992:self.clients.add(internal)
                        except (OSError,ValueError,struct.error,AssertionError):pass
                    at=blob.find(marker,at+8)
        return len(self.clients)

    def state(self, client):
        """双读校验队列字段及原生互斥锁。@param client 候选地址。@return 有效字段快照。"""
        for _ in range(8):
            one=self.read(client,248);two=self.read(client,248)
            if one==two and struct.unpack_from('<i',one,172)[0]==0:break
        else:raise ValueError('原生队列正在变化')
        source=struct.unpack_from('<i',one,16)[0];length,capacity=struct.unpack_from('<QQ',one,120)
        size,drops,reported=struct.unpack_from('<qqq',one,136)
        max_events,max_bytes=struct.unpack_from('<qq',one,96)
        require(0<=length<=capacity<=10000000 and 0<=size<=max_bytes<=1073741824)
        require(0<max_events<=10000000 and 0<=drops and 0<=reported)
        done=struct.unpack_from('<Q',one,200)[0]
        closed=struct.unpack('<I',self.read(done+28,4))[0];require(closed in [0,1])
        return {'client':hex(client),'source':source,'buffered_events':length,'buffered_bytes':size,
            'buffer_full_drops':drops,'reported_buffer_full_drops':reported,'done_closed':bool(closed),
            'upload_period_ns':struct.unpack_from('<q',one,56)[0],'max_buffered_events':max_events,'max_buffered_bytes':max_bytes}

    def snapshot(self):
        """读取所有已定位候选。@return 带代次的只读快照。"""
        require(self.pid==self.bridge.native_pid and self.generation==self.bridge.generation)
        states=[];errors=[]
        for client in sorted(self.clients):
            try:states.append(self.state(client))
            except (OSError,ValueError,AssertionError) as exc:errors.append({'client':hex(client),'error':type(exc).__name__})
        return {'ns':time.monotonic_ns(),'pid':self.pid,'generation':self.generation,'clients':states,'errors':errors}

    def close(self):
        """关闭只读内存句柄。@return 无返回值。"""
        os.close(self.fd)
