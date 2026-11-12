# Engineering contract: WEBCOLORS-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add webcolors.accessibility relative_luminance, contrast_ratio, meets_contrast and contrast_on. Implement the declared sRGB 0.04045 transfer breakpoint, weights .2126/.7152/.0722 and raw (Lmax+.05)/(Lmin+.05) ratio. Validate exact integer RGB channels; never silently clamp invalid measurements. Threshold 1..21 is explicit and finite; compare without rounding first. Ordinary luminance/ratio reject transparent RGBA. contrast_on accepts prior RGBA and an explicit opaque background, performs declared encoded-sRGB alpha compositing with nearest-byte half-up quantization and measures the resulting RGB; never guess a white background. Preserve legacy conversion and avoid claims that a color ratio certifies an entire UI.

Deliver real implementation, original-failing public tests at library/tests/test_development_webcolors_05_dev.py, and English compatibility documentation at library/docs/development-webcolors-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/webcolors/accessibility.py
- library/tests/test_development_webcolors_05_dev.py
- library/docs/development-webcolors-05-dev.md
