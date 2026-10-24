# Engineering contract: DE-LAYERS-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement dotenv.layers.load_layers(sources, *, environment=None, override=True, interpolate=True), accepting a finite iterable of uniquely named (name,text) layers. Strictly parse all layers before returning, merge in order using last definition per layer, resolve variables against explicit environment and previously resolved keys with pinned override precedence. Return immutable LayeredValues(values, origins); each origin is (layer_name, original_line). Do not read or mutate ambient os.environ or input mappings; unknown variables and defaults follow pinned parse_variables semantics. Preserve valueless keys and raw values when disabled.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_de_layers_dev.py and concise English compatibility documentation at library/docs/development-de-layers-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/dotenv/layers.py
- library/development_tests/test_development_de_layers_dev.py
- library/docs/development-de-layers-dev.md
