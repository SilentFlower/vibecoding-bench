import mistune

text = open("document.md", encoding="utf-8").read()
print(mistune.markdown(text))
print(mistune.html(text))
