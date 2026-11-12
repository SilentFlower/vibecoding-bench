from decouple import Config, Csv

print(Csv()("coffee#roast,tea"))
print(Csv()(r"\d+,tea"))
print(Csv()("coffee,,tea"))
print(Csv()('"coffee, beans",tea'))
print(Csv(cast=int, post_process=tuple)("1, 2"))

config = Config({"VB_CASE_LIST": r"coffee#roast,,\d+"})

