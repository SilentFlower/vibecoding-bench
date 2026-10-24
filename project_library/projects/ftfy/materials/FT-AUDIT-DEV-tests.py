"""公开真实文本修复审计回归。"""
import hashlib
from dataclasses import FrozenInstanceError
import pytest
from ftfy import TextFixerConfig,apply_plan
from ftfy.audit import repair

def test_actual_plan_replays_result_and_original_is_hashed():
    source='cafÃ© ﬁ';result=repair(source)
    assert result.text=='café fi' and result.changed and apply_plan(source,list(result.explanation))==result.text
    assert result.source_sha256==hashlib.sha256(source.encode()).hexdigest() and result.input_length==len(source)

def test_disabled_explanation_preserves_explicit_policy():
    result=repair('中文 cafÃ©',TextFixerConfig(explain=False,decode_inconsistent_utf8=False))
    assert result.text=='中文 cafÃ©' and not result.changed and result.explanation is None

def test_unchanged_text_keeps_empty_plan_and_frozen_result():
    result=repair('plain')
    assert not result.changed and result.explanation==()
    with pytest.raises(FrozenInstanceError): result.changed=True

def test_disabled_ligature_policy_is_kept_with_explanation():
    result=repair('ﬁ',TextFixerConfig(fix_latin_ligatures=False))
    assert result.text=='ﬁ' and not result.changed
