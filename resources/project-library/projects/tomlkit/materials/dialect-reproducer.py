from tomlkit import parse
import tomllib

# This consumer is explicitly Python 3.12 (TOML 1.0).
source = 'v = "\\e"\n'
print(repr(parse(source)["v"]))
print(tomllib.loads(source))
