# 用户的仓储类，用于管理用户的创建、查询、验证等方法

import sqlite3

from app.models.crypto import hash_password, new_salt
from app.models.db import get_connection


class UserRepository:
    @staticmethod
    def create_user(username: str, password: str) -> bool:
        salt = new_salt()
        password_hash = hash_password(password, salt)

        try:
            with get_connection() as conn:
                conn.execute(
                    "insert into users (username,password_hash,salt) values (?,?,?)",
                    (username, password_hash, salt.hex()),
                )

            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def get_user_by_username(username: str):
        with get_connection() as conn:
            row = conn.execute(
                "select id,username,password_hash,salt from users where username=?",
                (username,),
            ).fetchone()
        return row

    @staticmethod
    def verify_user(username: str, password: str) -> bool:
        row = UserRepository.get_user_by_username(username)
        if not row:
            return False

        salt = bytes.fromhex(row["salt"])
        return hash_password(password, salt) == row["password_hash"]
