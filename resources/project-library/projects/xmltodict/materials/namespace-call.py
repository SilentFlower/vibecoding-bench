import xmltodict

xml = open("order-namespaced.xml", encoding="utf-8").read()
document = xmltodict.parse(xml, process_namespaces=True)
print(document["orders"]["order"]["qty"])
