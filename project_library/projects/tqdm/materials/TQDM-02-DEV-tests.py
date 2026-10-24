"""管道分隔符跨块时仍精确透传、计数与逐记录回调。"""
import io
from tqdm.cli import posix_pipe


def test_multibyte_delimiter_at_every_chunk_boundary():
    """UTF8分隔符不能被拆成两段普通记录内容。@return None。"""
    raw='1é2é3'.encode();delimiter='é'.encode()
    for size in range(1,len(raw)+1):
        output=io.BytesIO();counts=[]
        posix_pipe(io.BytesIO(raw),output,delim=delimiter,buf_size=size,callback=counts.append)
        assert output.getvalue()==raw and sum(counts)==3


def test_numeric_callbacks_consecutive_tail_and_byte_mode():
    """数字更新收到完整记录，连续与末尾分隔计数政策保持。@return None。"""
    raw='1é2é3'.encode();output=io.BytesIO();values=[]
    posix_pipe(io.BytesIO(raw),output,delim='é'.encode(),buf_size=2,callback=lambda item:values.append(int(item)),callback_len=False)
    assert sum(values)==6 and output.getvalue()==raw
    output=io.BytesIO();records=[]
    posix_pipe(io.BytesIO(b'a||b|'),output,delim=b'|',buf_size=1,callback=records.append,callback_len=False)
    assert records==[b'a',b'',b'b'] and output.getvalue()==b'a||b|'
    output=io.BytesIO();counts=[]
    posix_pipe(io.BytesIO(raw),output,delim=b'',buf_size=2,callback=counts.append)
    assert sum(counts)==len(raw) and output.getvalue()==raw

