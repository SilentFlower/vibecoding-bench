from mistune import create_markdown, markdown
from mistune.renderers.markdown import MarkdownRenderer

source = "Coffee __beans__.\n"
rewritten = create_markdown(renderer=MarkdownRenderer())(source)
print(repr(source), repr(rewritten))
print(markdown(source) == markdown(rewritten))
