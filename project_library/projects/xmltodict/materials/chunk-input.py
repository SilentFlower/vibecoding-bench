from xmltodict import parse

chunks = ["<orders>", "<order id='A'><qty>2</qty></order>", "</orders>"]
print(parse(chunk for chunk in chunks))
print(parse(iter(chunks)))
