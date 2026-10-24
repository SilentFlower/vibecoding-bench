"Public regression tests for FT-ATOMIC-FILE-DEV; the complete business contract is in materials/FT-ATOMIC-FILE-DEV-contract.md."
import pytest
from ftfy.atomic import fix_file_atomic

def test_in_place_repair_preserves_permissions_and_counts(tmp_path):
    path=tmp_path/'text.txt';source='cafÃ©\r\nﬁ';path.write_text(source);path.chmod(0o640)
    result=fix_file_atomic(path)
    assert path.read_bytes()=='café\nfi'.encode() and result.changed and result.input_chars==len(source)
    assert result.output_chars==len('café\nfi') and path.stat().st_mode&0o777==0o640

def test_explicit_legacy_encoding_writes_utf8_without_claiming_text_change(tmp_path):
    source=tmp_path/'latin.txt';source.write_bytes('café'.encode('latin-1'));target=tmp_path/'utf8.txt'
    result=fix_file_atomic(source,target,encoding='latin-1')
    assert target.read_bytes()=='café'.encode() and not result.changed

def test_decode_failure_preserves_existing_target_and_removes_temp(tmp_path):
    source=tmp_path/'bad';source.write_bytes(b'\xff');target=tmp_path/'target';target.write_bytes(b'old')
    with pytest.raises(UnicodeDecodeError): fix_file_atomic(source,target)
    assert target.read_bytes()==b'old' and len(list(tmp_path.iterdir()))==2

def test_late_line_budget_failure_keeps_original_file(tmp_path):
    path=tmp_path/'text';path.write_text('ok\n'+'x'*50)
    with pytest.raises(ValueError): fix_file_atomic(path,max_line_length=10)
    assert path.read_text()=='ok\n'+'x'*50 and len(list(tmp_path.iterdir()))==1
