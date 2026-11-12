from io import StringIO
from dotenv import dotenv_values, load_dotenv

text = "BASE=file\nDERIVED=${BASE}/data\nEMPTY=\nBARE\n"
values = dotenv_values(stream=StringIO(text))
loaded = load_dotenv(stream=StringIO(text))
overridden = load_dotenv(stream=StringIO(text), override=True)
