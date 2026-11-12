from pathlib import Path
from tempfile import TemporaryDirectory
from decouple import Config, RepositoryEnv

with TemporaryDirectory() as directory:
    path = Path(directory) / ".env"
    path.write_text("VB_CASE_LABEL=first\n", encoding="utf-8")
    config = Config(RepositoryEnv(str(path)))
    print(config("VB_CASE_LABEL"))
    path.write_text("VB_CASE_LABEL=second\n", encoding="utf-8")
    print(config("VB_CASE_LABEL"))
    print(Config(RepositoryEnv(str(path)))("VB_CASE_LABEL"))
