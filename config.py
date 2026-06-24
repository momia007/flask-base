import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "default_secret")
    GOOGLE_SHEETS_KEY = os.getenv("GOOGLE_SHEETS_KEY")
