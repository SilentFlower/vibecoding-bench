"Public regression tests for BF-TYPEERROR-DEV; the complete business contract is in materials/BF-TYPEERROR-DEV-contract.md."
import pytest
import backoff


def test_dynamic_configuration_typeerror():
    "Verify dynamic configuration typeerror."
    calls = []
    failure = TypeError('config body')
    def broken():
        "Support the public regression through broken."
        raise failure
    target = backoff.on_predicate(backoff.constant, max_tries=broken, logger=None)(lambda: calls.append(1) or 3)
    with pytest.raises(TypeError) as result:
        target()
    assert result.value is failure and calls == []


def test_jitter_body_typeerror():
    "Verify jitter body typeerror."
    calls = []
    failure = TypeError('jitter body')
    def jitter(value):
        "Support the public regression through jitter."
        calls.append(value)
        raise failure
    target = backoff.on_predicate(backoff.constant, interval=0, max_tries=2, jitter=jitter, logger=None)(lambda: False)
    with pytest.raises(TypeError) as result:
        target()
    assert result.value is failure and calls == [0]


def test_legacy_jitter_and_runtime():
    "Verify legacy jitter and runtime."
    calls = []
    target = backoff.on_predicate(backoff.constant, interval=0, max_tries=2, jitter=lambda: 0, logger=None)(lambda: calls.append(1) or False)
    with pytest.warns(DeprecationWarning):
        assert target() is False
    assert len(calls) == 2
