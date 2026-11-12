import json
import mistune

tokens = mistune.markdown("# 咖啡\n\nCoffee **beans**.", renderer="ast")
print(type(tokens))
print(json.dumps(tokens, ensure_ascii=False))
