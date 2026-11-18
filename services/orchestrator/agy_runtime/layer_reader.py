"""从原生组合客户端的真实接口与持有字段采集遥测各层。"""
from .validation import require
import json
import os
from pathlib import Path
import struct
import time
from .queue_reader import QueueReader
ROOT=Path(__file__).parent/'resources'


class LayerReader(QueueReader):
    """只读追踪组合客户端、延迟脱敏、CEL及Clearcut内部客户端。"""

    def __init__(self, bridge):
        """绑定固定原生代次。@param bridge 本代桥接。@return 无返回值。"""
        super().__init__(bridge);self.owners=set();self.composites=set();self.discovery_errors=[];self.skipped_pages=0
        self.itabs=json.loads((ROOT/'telemetry-itabs.json').read_text())

    def pointer(self, address):
        """读取本代指针槽位。@param address 槽位。@return 指针。"""
        return struct.unpack('<Q',self.read(address,8))[0]

    def add_owner(self, wrapper):
        """验证真实客户端字段并登记所有权。@param wrapper telemetry.Client。@return 无返回值。"""
        owner=self.pointer(wrapper)
        if self.pointer(owner)!=self.base+0xcb6de70:raise ValueError('客户端logger接口不匹配')
        logger=self.pointer(owner+8);client=self.pointer(logger)
        require(self.state(client)['source']==2747)
        self.owners.add(owner);self.clients.add(client);self.origins.setdefault(hex(client),set()).add('telemetry.Client.clearcutClient.logger')

    def discover(self):
        """按已驻留页扫描真实接口，随后沿原生持有关系读取。@return 原生拥有者数。"""
        markers=[(i['concrete'],struct.pack('<Q',self.base+int(i['itab'],16))) for i in self.itabs]
        pagemap=os.open(f'/proc/{self.pid}/pagemap',os.O_RDONLY)
        try:
            for row in Path(f'/proc/{self.pid}/maps').read_text().splitlines():
                cols=row.split();lo,hi=[int(v,16) for v in cols[0].split('-')]
                if cols[1][:2]!='rw' or len(cols)>5 and cols[-1] not in ['[heap]','[stack]']:continue
                for start in range(lo,hi,262144):
                    end=min(start+262144,hi);page_count=(end-start)//4096
                    raw=os.pread(pagemap,page_count*8,start//4096*8)
                    if len(raw)!=page_count*8:continue
                    pages=struct.unpack('<'+'Q'*page_count,raw);index=0
                    while index<page_count:
                        if not pages[index]>>63:self.skipped_pages+=1;index+=1;continue
                        begin=index
                        while index<page_count and pages[index]>>63:index+=1
                        address=start+begin*4096
                        try:blob=self.read(address,(index-begin)*4096)
                        except (OSError,ValueError):continue
                        self.scan_bytes+=len(blob)
                        for concrete,marker in markers:
                            at=blob.find(marker)
                            while at>=0:
                                if (address+at)%8==0:
                                    try:
                                        value=self.pointer(address+at+8)
                                        if concrete=='telemetry.Client':self.add_owner(value)
                                        elif concrete=='telemetryinterface.CompositeTelemetryClient':
                                            header=self.read(value,88);valid=False
                                            for offset in [24,48]:
                                                ptr,length,capacity=struct.unpack_from('<QQQ',header,offset)
                                                if not 0<=length<=capacity<=64:raise ValueError('组合客户端数量异常')
                                                for n in range(length):
                                                    tab,data=struct.unpack('<QQ',self.read(ptr+n*16,16))
                                                    if tab==self.base+0xcba83d8:self.add_owner(data);valid=True
                                            if valid:self.composites.add(value)
                                    except (OSError,ValueError,AssertionError,struct.error):pass
                                at=blob.find(marker,at+8)
        finally:os.close(pagemap)
        return len(self.owners)

    def state(self, client):
        """读取由类型持有关系确认的客户端字段。@param client 真实客户端。@return 队列及原生预算。"""
        for _ in range(8):
            one=self.read(client,248);two=self.read(client,248)
            if one==two and struct.unpack_from('<i',one,172)[0]==0:break
        else:raise ValueError('原生队列正在变化')
        source=struct.unpack_from('<i',one,16)[0];length,capacity=struct.unpack_from('<QQ',one,120)
        size,drops,reported=struct.unpack_from('<qqq',one,136);max_events,max_bytes=struct.unpack_from('<qq',one,96)
        require(source in [2747,2992,327] and 0<=length<=capacity<=10000000 and size>=0 and drops>=0 and reported>=0)
        done=struct.unpack_from('<Q',one,200)[0];closed=struct.unpack('<I',self.read(done+28,4))[0];require(closed in [0,1])
        return {'client':hex(client),'source':source,'buffered_events':length,'buffered_bytes':size,'buffer_full_drops':drops,
            'reported_buffer_full_drops':reported,'done_closed':bool(closed),'upload_period_ns':struct.unpack_from('<q',one,56)[0],
            'max_buffered_events':max_events,'max_buffered_bytes':max_bytes}

    def snapshot(self):
        """读取实际持有的队列与原生停止状态。@return 各层采样与错误。"""
        layers=[];errors=[]
        for owner in sorted(self.owners):
            try:
                raw=self.read(owner,48);cel=struct.unpack_from('<Q',raw,16)[0];deferred=struct.unpack_from('<Q',raw,40)[0]
                row={'owner':hex(owner),'cel_present':bool(cel),'deferred_present':bool(deferred)}
                if deferred:
                    first=self.read(deferred,48);second=self.read(deferred,48)
                    if first!=second or struct.unpack_from('<i',first,8)[0]:raise ValueError('延迟脱敏采样变化')
                    length,capacity=struct.unpack_from('<QQ',first,32);require(0<=length<=capacity<=10000000)
                    row['deferred']={'events':length,'capacity':capacity,'timed_out':bool(first[16]),'resolved':bool(first[17]),'closed':bool(first[18]),'timeout_ns':struct.unpack_from('<q',first)[0]}
                if cel:
                    row['cel']={'pointer':hex(cel),'in_flight_events':struct.unpack('<q',self.read(cel+56,8))[0],'shutdown_once':struct.unpack('<I',self.read(cel+76,4))[0]}
                    cc=self.pointer(cel)
                    if cc:self.clients.add(cc);self.origins.setdefault(hex(cc),set()).add('AntigravityClient.celClient.cc')
                layers.append(row)
            except (OSError,ValueError,AssertionError) as exc:errors.append({'owner':hex(owner),'error':str(exc)})
        meta=[]
        for client in list(self.clients):
            try:
                pointer=self.pointer(client+240)
                if not pointer:continue
                raw=self.read(pointer,192);internal=struct.unpack_from('<Q',raw,144)[0]
                if internal:self.clients.add(internal);self.origins.setdefault(hex(internal),set()).add('Clearcut.metalogger.internalClient')
                meta.append({'pointer':hex(pointer),'monitored_client':hex(client),'has_new_data':bool(raw[88]),'current_window_size':struct.unpack_from('<q',raw,104)[0],'stopped':bool(raw[184]),'internal_client':hex(internal)})
            except (OSError,ValueError) as exc:errors.append({'client':hex(client),'error':str(exc)})
        result=super().snapshot();result.update(layers=layers,metaloggers=meta,layer_errors=errors,composites=[hex(x) for x in sorted(self.composites)])
        return result
