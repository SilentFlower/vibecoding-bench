# Engineering contract: CONFIGOBJ-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add ConfigObj.validate_report(validator, *, apply=False) using actual validate(preserve_errors=True) and flatten_errors. Always return JSON-safe valid:boolean, issues:[{path:list,kind:string}], changed_paths, defaulted_paths and applied. valid must only accept the literal successful True result, never a truthy failure dict. Report complete nested paths and error class/missing markers without error messages or configuration values. Default dry mode validates a raw-preserving clone and leaves source values/comments/options unchanged; explicit apply=True uses existing validation conversion behavior. Record type conversions and applied default paths, keeping validate API unchanged.

Deliver meaningful original-failing public regression tests at library/tests/test_development_configobj_o05_dev.py and concise English compatibility documentation at library/docs/development-configobj-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/configobj/__init__.py
- library/tests/test_development_configobj_o05_dev.py
- library/docs/development-configobj-o05-dev.md
