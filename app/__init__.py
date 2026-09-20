from os import path

from dotenv import load_dotenv

root_dir = path.dirname(__file__)

result = load_dotenv(path.join(root_dir, ".env"))
