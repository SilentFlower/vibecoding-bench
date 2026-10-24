"""文本摘要稳定，不把原始编码差异或Unicode形式偷偷合并。"""
import hashlib
from charset_normalizer.models import CharsetMatch

def test_same_text_different_raw():
    """相同文字不同输入编码，text相同raw不同。@return None。"""
    text = 'café'
    one = CharsetMatch(text.encode('utf-8'), 'utf_8', 0.0, False, [])
    two = CharsetMatch(text.encode('latin-1'), 'latin_1', 0.0, False, [])
    assert one.stable_digest() == two.stable_digest() == hashlib.sha256(text.encode()).hexdigest()
    assert one.stable_digest(mode='raw') != two.stable_digest(mode='raw')

def test_unicode_policy_and_snapshot():
    """Unicode归一化显式，可变源仍保持已冻结事实。@return None。"""
    source = bytearray('é'.encode())
    one = CharsetMatch(source, 'utf_8', 0.0, False, [])
    two = CharsetMatch('e\u0301'.encode(), 'utf_8', 0.0, False, [])
    source.clear()
    assert one.stable_digest() != two.stable_digest()
    assert one.stable_digest(normalization='NFC') == two.stable_digest(normalization='NFC')

def test_process_stability_and_invalid():
    """不同hash种子下真实方法返回同一摘要。@return None。"""
    import os
    import subprocess
    import sys
    import pytest
    code = "from charset_normalizer.models import CharsetMatch; print(CharsetMatch(b'abc','ascii',0.0,False,[]).stable_digest())"
    outputs = [subprocess.check_output([sys.executable, '-c', code], env=dict(os.environ, PYTHONHASHSEED=seed)) for seed in ['1', '2']]
    assert outputs[0] == outputs[1]
    with pytest.raises(ValueError): CharsetMatch(b'', 'ascii', 0.0, False, []).stable_digest(algorithm='unknown')
