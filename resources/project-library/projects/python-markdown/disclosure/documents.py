from markdown import Markdown
from markdown.extensions.footnotes import FootnoteExtension

renderer = Markdown(extensions=[FootnoteExtension()])
print(renderer.convert("Coffee[^a]\n\n[^a]: first-note"))
print(renderer.convert("Tea[^a]"))
renderer.reset()
print(renderer.convert("Tea[^a]"))
