from xmltodict import unparse

print(unparse({"root": {"omitted": [], "none": None, "explicit": [None], "text": [""]}}))
