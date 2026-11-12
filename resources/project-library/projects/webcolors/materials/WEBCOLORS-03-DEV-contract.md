# Engineering contract: WEBCOLORS-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add webcolors.rgba with immutable validated RGBA(red,green,blue,alpha=255), exact 4/8-digit hex_to_rgba, lossless 8-digit rgba_to_hex, rgb_to_rgba and opaque-only rgba_to_rgb. All channels are integer bytes 0..255 (bool/float rejected); zero-alpha hidden RGB is retained. Do not alter legacy RGB or HTML simple-color functions to accept/drop alpha. Reject malformed lengths, suffixes and whitespace; do not clamp silently or use a white background implicitly. Provide complete source implementation, public roundtrip/error tests and English compatibility documentation.

Deliver real implementation, original-failing public tests at library/tests/test_development_webcolors_03_dev.py, and English compatibility documentation at library/docs/development-webcolors-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/webcolors/rgba.py
- library/tests/test_development_webcolors_03_dev.py
- library/docs/development-webcolors-03-dev.md
