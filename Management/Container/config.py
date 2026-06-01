from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
# 统一使用项目根目录下的 database.db，保证登录、集装箱、堆场模块访问同一个 SQLite 文件。
DB_PATH = (BASE_DIR.parents[1] / 'database.db').as_posix()


class Config:
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'ctms-course-design-secret'
