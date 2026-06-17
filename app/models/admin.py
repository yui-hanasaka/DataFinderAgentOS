import hashlib
import secrets
import sqlite3

from app.models.db import get_connection


PER_PAGE = 20


def _hash_password(password: str, salt: bytes) -> str:
	dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
	return dk.hex()


def _page_offset(page: int, per_page: int = PER_PAGE) -> int:
	return (max(page, 1) - 1) * per_page


def _like(keyword: str) -> str:
	return f"%{keyword.strip()}%"


class AdminRepository:
	@staticmethod
	def get_admin_by_username(username: str):
		with get_connection() as conn:
			return conn.execute(
				"""
				select
					au.id,
					au.username,
					au.password_hash,
					au.salt,
					au.display_name,
					au.is_super,
					au.status,
					ar.role_code,
					ar.role_name
				from admin_users au
				left join admin_roles ar on ar.id = au.role_id
				where au.username=?
				""",
				(username,)
			).fetchone()

	@staticmethod
	def verify_admin(username: str, password: str) -> bool:
		row = AdminRepository.get_admin_by_username(username)
		if not row or row["status"] != "enabled":
			return False

		salt = bytes.fromhex(row["salt"])
		return _hash_password(password, salt) == row["password_hash"]

	@staticmethod
	def list_roles(keyword: str = "", page: int = 1, per_page: int = PER_PAGE):
		where = ""
		params = []
		if keyword.strip():
			where = "where role_code like ? or role_name like ? or ifnull(description, '') like ?"
			params = [_like(keyword), _like(keyword), _like(keyword)]

		with get_connection() as conn:
			total = conn.execute(f"select count(*) from admin_roles {where}", params).fetchone()[0]
			rows = conn.execute(
				f"""
				select * from admin_roles
				{where}
				order by is_system desc, id asc
				limit ? offset ?
				""",
				params + [per_page, _page_offset(page, per_page)]
			).fetchall()
		return rows, total

	@staticmethod
	def list_all_roles():
		with get_connection() as conn:
			return conn.execute(
				"select * from admin_roles where status='enabled' order by is_system desc, id asc"
			).fetchall()

	@staticmethod
	def get_role(role_id: int):
		with get_connection() as conn:
			return conn.execute("select * from admin_roles where id=?", (role_id,)).fetchone()

	@staticmethod
	def create_role(role_code: str, role_name: str, role_type: str, description: str, menu_ids):
		try:
			with get_connection() as conn:
				cur = conn.execute(
					"""
					insert into admin_roles(role_code, role_name, role_type, description)
					values(?, ?, ?, ?)
					""",
					(role_code, role_name, role_type, description)
				)
				new_id = cur.lastrowid
				assert new_id is not None
				AdminRepository._replace_role_menus(conn, new_id, menu_ids)
			return True, None
		except sqlite3.IntegrityError:
			return False, "角色编码已存在"

	@staticmethod
	def update_role(role_id: int, role_name: str, role_type: str, description: str, status: str, menu_ids):
		with get_connection() as conn:
			role = conn.execute("select is_system from admin_roles where id=?", (role_id,)).fetchone()
			if not role:
				return False, "角色不存在"
			if role["is_system"]:
				return False, "系统内置角色不允许修改"
			conn.execute(
				"""
				update admin_roles
				set role_name=?, role_type=?, description=?, status=?, updated_at=datetime('now')
				where id=?
				""",
				(role_name, role_type, description, status, role_id)
			)
			AdminRepository._replace_role_menus(conn, role_id, menu_ids)
		return True, None

	@staticmethod
	def delete_role(role_id: int):
		with get_connection() as conn:
			role = conn.execute("select is_system from admin_roles where id=?", (role_id,)).fetchone()
			if not role:
				return False, "角色不存在"
			if role["is_system"]:
				return False, "系统内置角色不允许删除"
			used = conn.execute("select count(*) from admin_users where role_id=?", (role_id,)).fetchone()[0]
			if used:
				return False, "该角色已被用户使用，不能删除"
			conn.execute("delete from admin_role_menus where role_id=?", (role_id,))
			conn.execute("delete from admin_roles where id=?", (role_id,))
		return True, None

	@staticmethod
	def list_menus(keyword: str = "", page: int = 1, per_page: int = PER_PAGE):
		where = ""
		params = []
		if keyword.strip():
			where = "where menu_code like ? or menu_name like ? or ifnull(url, '') like ?"
			params = [_like(keyword), _like(keyword), _like(keyword)]

		with get_connection() as conn:
			total = conn.execute(f"select count(*) from admin_menus {where}", params).fetchone()[0]
			rows = conn.execute(
				f"""
				select * from admin_menus
				{where}
				order by sort_order asc, id asc
				limit ? offset ?
				""",
				params + [per_page, _page_offset(page, per_page)]
			).fetchall()
		return rows, total

	@staticmethod
	def list_all_menus():
		with get_connection() as conn:
			return conn.execute(
				"select * from admin_menus where status='enabled' order by sort_order asc, id asc"
			).fetchall()

	@staticmethod
	def get_menu(menu_id: int):
		with get_connection() as conn:
			return conn.execute("select * from admin_menus where id=?", (menu_id,)).fetchone()

	@staticmethod
	def create_menu(menu_code: str, menu_name: str, icon: str, url: str, sort_order: int, parent_id: int = 0):
		try:
			with get_connection() as conn:
				conn.execute(
					"""
					insert into admin_menus(parent_id, menu_code, menu_name, icon, url, sort_order)
					values(?, ?, ?, ?, ?, ?)
					""",
					(parent_id, menu_code, menu_name, icon, url, sort_order)
				)
			return True, None
		except sqlite3.IntegrityError:
			return False, "功能编码已存在"

	@staticmethod
	def update_menu(menu_id: int, menu_name: str, icon: str, url: str, sort_order: int, status: str, parent_id: int = 0):
		with get_connection() as conn:
			conn.execute(
				"""
				update admin_menus
				set parent_id=?, menu_name=?, icon=?, url=?, sort_order=?, status=?, updated_at=datetime('now')
				where id=?
				""",
				(parent_id, menu_name, icon, url, sort_order, status, menu_id)
			)
		return True, None

	@staticmethod
	def delete_menu(menu_id: int):
		with get_connection() as conn:
			children = conn.execute("select count(*) from admin_menus where parent_id=?", (menu_id,)).fetchone()[0]
			if children:
				return False, "存在子功能，不能删除"
			conn.execute("delete from admin_role_menus where menu_id=?", (menu_id,))
			conn.execute("delete from admin_menus where id=?", (menu_id,))
		return True, None

	@staticmethod
	def get_role_menu_ids(role_id: int):
		with get_connection() as conn:
			rows = conn.execute("select menu_id from admin_role_menus where role_id=?", (role_id,)).fetchall()
		return [row["menu_id"] for row in rows]

	@staticmethod
	def _replace_role_menus(conn, role_id: int, menu_ids):
		conn.execute("delete from admin_role_menus where role_id=?", (role_id,))
		ids = [(role_id, int(menu_id)) for menu_id in menu_ids if str(menu_id).isdigit()]
		if ids:
			conn.executemany(
				"insert or ignore into admin_role_menus(role_id, menu_id) values(?, ?)",
				ids
			)

	@staticmethod
	def list_users(keyword: str = "", page: int = 1, per_page: int = PER_PAGE):
		where = ""
		params = []
		if keyword.strip():
			where = "where au.username like ? or au.display_name like ? or ar.role_name like ?"
			params = [_like(keyword), _like(keyword), _like(keyword)]

		with get_connection() as conn:
			total = conn.execute(
				f"select count(*) from admin_users au left join admin_roles ar on ar.id=au.role_id {where}",
				params
			).fetchone()[0]
			rows = conn.execute(
				f"""
				select au.id, au.username, au.display_name, au.role_id, au.is_super, au.status,
					au.created_at, ar.role_name, ar.role_code
				from admin_users au
				left join admin_roles ar on ar.id=au.role_id
				{where}
				order by au.is_super desc, au.id asc
				limit ? offset ?
				""",
				params + [per_page, _page_offset(page, per_page)]
			).fetchall()
		return rows, total

	@staticmethod
	def get_user(user_id: int):
		with get_connection() as conn:
			return conn.execute(
				"select id, username, display_name, role_id, is_super, status from admin_users where id=?",
				(user_id,)
			).fetchone()

	@staticmethod
	def create_user(username: str, password: str, display_name: str, role_id: int, status: str):
		salt = secrets.token_bytes(16)
		try:
			with get_connection() as conn:
				conn.execute(
					"""
					insert into admin_users(username, password_hash, salt, display_name, role_id, status)
					values(?, ?, ?, ?, ?, ?)
					""",
					(username, _hash_password(password, salt), salt.hex(), display_name, role_id, status)
				)
			return True, None
		except sqlite3.IntegrityError:
			return False, "用户名已存在"

	@staticmethod
	def update_user(user_id: int, display_name: str, role_id: int, status: str, password: str = ""):
		with get_connection() as conn:
			user = conn.execute("select username, is_super from admin_users where id=?", (user_id,)).fetchone()
			if not user:
				return False, "用户不存在"
			if user["username"] == "admin" and status != "enabled":
				return False, "admin 不允许禁用"
			if password:
				salt = secrets.token_bytes(16)
				conn.execute(
					"""
					update admin_users
					set display_name=?, role_id=?, status=?, password_hash=?, salt=?, updated_at=datetime('now')
					where id=?
					""",
					(display_name, role_id, status, _hash_password(password, salt), salt.hex(), user_id)
				)
			else:
				conn.execute(
					"""
					update admin_users
					set display_name=?, role_id=?, status=?, updated_at=datetime('now')
					where id=?
					""",
					(display_name, role_id, status, user_id)
				)
		return True, None

	@staticmethod
	def delete_user(user_id: int):
		with get_connection() as conn:
			user = conn.execute("select username from admin_users where id=?", (user_id,)).fetchone()
			if not user:
				return False, "用户不存在"
			if user["username"] == "admin":
				return False, "admin 不允许删除"
			conn.execute("delete from admin_users where id=?", (user_id,))
		return True, None
