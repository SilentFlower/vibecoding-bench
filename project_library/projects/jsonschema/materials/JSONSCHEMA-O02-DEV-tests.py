"Public regression tests for JSONSCHEMA-O02-DEV; the complete business contract is in materials/JSONSCHEMA-O02-DEV-contract.md."
from jsonschema.exceptions import ValidationError
from jsonschema import Draft202012Validator
import ast

def test_newline_key_is_quoted_escaped_and_resolves_exact_key():
    "Verify newline key is quoted escaped and resolves exact key."
    instance={'x':2,'x\n':1};validator=Draft202012Validator({'properties':{'x\n':{'type':'string'}}})
    error=next(validator.iter_errors(instance));assert error.json_path=="$['x\\n']"
    key=ast.literal_eval(error.json_path[2:-1]);assert key=='x\n' and instance[key]==1

def test_quote_backslash_controls_unicode_and_empty_keys_round_trip():
    "Verify quote backslash controls unicode and empty keys round trip."
    for key in ["a'b",'a\\b','', '\t\r\n\b\f\x00\x1f','中文','2start']:
        error=ValidationError('bad',path=[key]);path=error.json_path
        assert path.startswith("$['") and not any(ord(char)<32 for char in path)
        assert ast.literal_eval(path[2:-1])==key

def test_identifiers_arrays_and_absolute_parent_paths_keep_original_semantics():
    "Verify identifiers arrays and absolute parent paths keep original semantics."
    child=ValidationError('bad',path=[2,'leaf\n']);parent=ValidationError('outer',path=['root'],context=[child])
    assert child.json_path=="$.root[2]['leaf\\n']" and list(child.absolute_path)==['root',2,'leaf\n']
    assert ValidationError('ok',path=['Alpha_2']).json_path=='$.Alpha_2'
