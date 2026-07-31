import os

from dotenv import load_dotenv


DEFAULT_NAVIGATOR_MODEL = "gpt-oss-20b"


def get_navigator_model() -> str:
    load_dotenv()
    return os.getenv("NAVIGATOR_MODEL", DEFAULT_NAVIGATOR_MODEL)
