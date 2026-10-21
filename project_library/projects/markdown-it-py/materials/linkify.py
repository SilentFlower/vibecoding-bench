from markdown_it import MarkdownIt

parser = MarkdownIt("commonmark", {"linkify": True})
print(parser.get_active_rules()["core"])
print(parser.render("Visit https://example.org/shop."))
parser.enable("linkify")
print(parser.render("Visit https://example.org/shop."))
