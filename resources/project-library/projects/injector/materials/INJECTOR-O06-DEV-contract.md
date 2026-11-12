# Engineering contract: INJECTOR-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Binder.bindings_snapshot(*,include_parents=True) returning frozen BindingInfo tuples for existing effective bindings only: interface, provider_type, scope, owner_depth, explicit and immutable multi-contribution provider/scope type metadata. Preserve child-over-parent precedence and current registration order, mark ImplicitBinding accurately and inspect _bindings directly under existing lock without get_binding/auto_bind/provider invocation. Never expose mutable Binding objects or business instances; later rebind does not mutate prior snapshots, and include_parents must be actual bool. Special ProviderOf/AssistedBuilder capabilities must not be auto-created merely by inspection.

Deliver meaningful original-failing public regression tests at library/tests/test_development_injector_o06_dev.py and concise English compatibility documentation at library/docs/development-injector-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/injector/__init__.py
- library/tests/test_development_injector_o06_dev.py
- library/docs/development-injector-o06-dev.md
