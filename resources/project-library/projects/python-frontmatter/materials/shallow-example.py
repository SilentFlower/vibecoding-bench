import frontmatter

defaults = {"theme": "light", "lang": "zh"}
text = "---\nsettings:\n  theme: dark\n---\n正文"
metadata, body = frontmatter.parse(text, settings=defaults)
print(metadata)
