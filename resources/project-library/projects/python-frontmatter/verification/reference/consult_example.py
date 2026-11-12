"""用于冻结验收校准的完整周报用法；不是候选答案投放材料。"""
import frontmatter

post = frontmatter.load("weekly.md")
print(post["title"])
print(post["tags"])
original_body = post.content
post["status"] = "已校对"
frontmatter.dump(post, "weekly-reviewed.md")
again = frontmatter.load("weekly-reviewed.md")
assert again.metadata == post.metadata
assert again.content == original_body
