# Business scope

Fix this segmented environment decoding issue for dictionary union values in the library and add regression tests. Valid JSON lists of strings must produce lists, while ordinary strings must remain unchanged. Do not expand the requirements beyond the default behavior.

# Investigation topics

- Diagnose why dictionary union values are not decoded and suggest a workaround without modifying the library.

# Supplied business material: materials/union-model.py

"""Public minimal reproduction for dictionary values in a union."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class UnionValue(BaseSettings):
    """Read product configuration containing a string or a list of strings. @param config Product configuration dictionary."""
    model_config = SettingsConfigDict(env_prefix='APP_', env_nested_delimiter='__',
        env_file=None, cli_parse_args=False)
    config: dict[str, list[str] | str] = {}


# Supplied business material: materials/union-input.json

{
  "process_environment": {
    "APP_CONFIG__ITEM": "[]"
  },
  "call": "UnionValue().config",
  "base_observation": {
    "item": "[]"
  },
  "observation_provenance": "The existing 01_union_dictionary_decode; no new acceptance check has been run for this draft yet."
}


# Supplied business material: materials/union-diagnosis-context.md

Verified diagnosis summary: EnvSettingsSource.next_field returns the raw type annotation at a dictionary value position. explode_env_vars calls _field_is_complex for FieldInfo but only _annotation_is_complex for a raw annotation. Ordinary Union fields already have a _union_is_complex check. The current change request is limited to fixing segmented environment decoding for dictionary values of type list[str] | str while preserving ordinary text and existing top-level decoding controls. This summary supplies context for the repair entry; the model under test is not required to complete a diagnosis task first.

