from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = (BASE_DIR / 'instance' / 'database.db').as_posix()


class Config:
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
