# 用户的仓储类，用于管理用户的创建、查询、验证等方法

import hashlib
import secrets
import sqlite3

from app.models.db import get_connection

def _hash_password(password:str,salt:bytes) -> str:
	dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
	return dk.hex()

class UserRepository:
	@staticmethod
	def create_user(username:str,password:str) -> bool:
		salt = secrets.token_bytes(16)
		password_hash = _hash_password(password,salt)

		try:
			with get_connection() as conn:
				conn.execute(
					"insert into users (username,password_hash,salt) values (?,?,?)",
					(username,password_hash,salt.hex())
				)

			return True
		except sqlite3.IntegrityError:
			return False

	@staticmethod
	def get_user_by_username(username:str):
		with get_connection() as conn:
			row = conn.execute(
				"select id,username,password_hash,salt from users where username=?",
				(username,)
			).fetchone()
		return row

	@staticmethod
	def verify_user(username:str,password:str) -> bool:
		row = UserRepository.get_user_by_username(username)
		if not row:
			return False

		salt = bytes.fromhex(row["salt"])
		return _hash_password(password,salt)==row["password_hash"]
