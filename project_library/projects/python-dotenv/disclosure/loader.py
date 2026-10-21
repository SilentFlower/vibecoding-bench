import os
from dotenv import load_dotenv

loaded = load_dotenv(config_path)
observed = (loaded, os.environ.get("APP_MODE"))
