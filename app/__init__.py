from dotenv import load_dotenv
from os import path

root_dir = path.dirname(__file__)

result = load_dotenv(path.join(root_dir, ".env"))
