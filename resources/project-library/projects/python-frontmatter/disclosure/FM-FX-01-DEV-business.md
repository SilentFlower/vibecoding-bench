# Business scope

Fix this reading issue. The document's content is a business summary field and must be preserved separately from the body; handler may also be a business field. Keep existing Post construction and ordinary document usage compatible, and add the necessary regression checks.
Full reproduction: import frontmatter; text = "---\ncontent: 备用摘要\n---\n正文"; frontmatter.loads(text) raises TypeError: Post.__init__() got multiple values for argument 'content'.
You may modify library/frontmatter, the related tests, and documentation. Preserve the existing flat output contract of Post.to_dict, and do not expand the scope to formatting preservation or deep merging.

# Investigation topics

- Obtain the necessary materials before diagnosing TypeError in the affected documents.

# Supplied business material: disclosure/unavailable.md

Additional context: I currently cannot obtain the failing document, calling code, or full exception. Explain what can be determined now, what is still missing, and how to verify it later. Do not guess a definite root cause.

