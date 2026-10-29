import frontmatter

text = "---\ncontent: 备用摘要\n---\n正文"
post = frontmatter.loads(text)
