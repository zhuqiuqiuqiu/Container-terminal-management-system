# -*- coding: utf-8 -*-
"""
数据访问层（DAO，Data Access Object）
======================================
这是后端的"数据访问层"：负责把后端的业务请求翻译成 SQL，对数据库进行读写。

职责范围（属于后端）：
    - 拿数据库连接
    - 按业务需求查询 / 更新数据库
    - 把查询结果封装成 Python dict 返回给业务层

不属于本文件的职责（属于数据库组）：
    - 数据库表结构设计 / 建表 SQL（见 init_db.py 中的临时实现）
    - 索引、约束、视图等数据库设计细节

正式部署时，建表工作由数据库组提供的 SQL 脚本完成，不再依赖 init_db.py。
"""

import sqlite3
import os

# 数据库文件路径：与本文件同目录，名为 user.db
# 正式部署时这里会替换为真实数据库的连接配置（如 MySQL/PostgreSQL 的 host/port/账号）
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user.db')


def get_connection():
    """
    获取一个 SQLite 数据库连接。

    说明：
        - 设置 row_factory 为 sqlite3.Row，使得查询结果可以像字典一样按列名访问
        - 调用方负责在使用完毕后关闭连接

    返回：
        sqlite3.Connection 对象
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def find_user_by_username(username):
    """
    按用户名查询用户。登录验证用的核心函数。

    参数：
        username 用户名

    返回：
        若查到则返回 dict（含 id/username/password/role/last_login_at）
        若查不到则返回 None
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, username, password, role, last_login_at "
            "FROM user WHERE username = ?",
            (username,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_last_login(user_id, login_time):
    """
    更新指定用户的最近登录时间。

    参数：
        user_id    用户主键
        login_time 登录时间字符串（YYYY-MM-DD HH:MM:SS）
    """
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE user SET last_login_at = ? WHERE id = ?",
            (login_time, user_id)
        )
        conn.commit()
    finally:
        conn.close()
