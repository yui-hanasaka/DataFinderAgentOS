import secrets
import sqlite3
from datetime import datetime

from app.models.crypto import hash_password
from app.models.db import get_connection

PER_PAGE = 20


def _page_offset(page: int, per_page: int = PER_PAGE) -> int:
    return (max(page, 1) - 1) * per_page


def _like(keyword: str) -> str:
    return f"%{keyword.strip()}%"


class AdminRepository:
    MAX_FAILED_ATTEMPTS = 5
    LOCK_DURATION_MINUTES = 15

    @staticmethod
    def get_admin_by_username(username: str):
        with get_connection() as conn:
            return conn.execute(
                """SELECT
                        au.id, au.username, au.password_hash, au.salt,
                        au.display_name, au.is_super, au.status,
                        au.failed_login_count, au.locked_until,
                        au.must_change_password, au.last_login_at,
                        ar.role_code, ar.role_name
                   FROM admin_users au
                   LEFT JOIN admin_roles ar ON ar.id = au.role_id
                   WHERE au.username=?""",
                (username,),
            ).fetchone()

    @staticmethod
    def record_failed_login(admin_id: int) -> None:
        """Increment failed_login_count; lock account when threshold reached."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT failed_login_count FROM admin_users WHERE id=?",
                (admin_id,),
            ).fetchone()
            if not row:
                return
            failed = (row["failed_login_count"] or 0) + 1
            if failed >= AdminRepository.MAX_FAILED_ATTEMPTS:
                conn.execute(
                    """UPDATE admin_users
                       SET failed_login_count=?,
                           locked_until=datetime('now','+'||?||' minutes')
                       WHERE id=?""",
                    (failed, AdminRepository.LOCK_DURATION_MINUTES, admin_id),
                )
            else:
                conn.execute(
                    "UPDATE admin_users SET failed_login_count=? WHERE id=?",
                    (failed, admin_id),
                )

    @staticmethod
    def record_successful_login(admin_id: int) -> None:
        """Reset lockout counters and stamp last_login_at."""
        with get_connection() as conn:
            conn.execute(
                """UPDATE admin_users
                   SET failed_login_count=0, locked_until=NULL,
                       last_login_at=datetime('now')
                   WHERE id=?""",
                (admin_id,),
            )

    @staticmethod
    def verify_admin(username: str, password: str) -> bool:
        row = AdminRepository.get_admin_by_username(username)
        if not row or row["status"] != "enabled":
            return False

        # H2: check lockout before verifying password
        # Use UTC — SQLite datetime('now') returns UTC
        if row["locked_until"]:
            locked = datetime.fromisoformat(row["locked_until"])
            from datetime import timezone

            if locked > datetime.now(timezone.utc).replace(tzinfo=None):
                return False  # still locked

        salt = bytes.fromhex(row["salt"])
        pwd_ok = hash_password(password, salt) == row["password_hash"]

        if pwd_ok:
            AdminRepository.record_successful_login(row["id"])
        else:
            AdminRepository.record_failed_login(row["id"])

        return pwd_ok

    @staticmethod
    def list_roles(keyword: str = "", page: int = 1, per_page: int = PER_PAGE):
        where = ""
        params = []
        if keyword.strip():
            where = "where role_code like ? or role_name like ? or ifnull(description, '') like ?"
            params = [_like(keyword), _like(keyword), _like(keyword)]

        with get_connection() as conn:
            total = conn.execute(
                f"select count(*) from admin_roles {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""SELECT * FROM admin_roles
                    {where}
                    ORDER BY is_system DESC, id ASC
                    LIMIT ? OFFSET ?""",
                params + [per_page, _page_offset(page, per_page)],
            ).fetchall()
        return rows, total

    @staticmethod
    def list_all_roles():
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM admin_roles WHERE status='enabled' ORDER BY is_system DESC, id ASC"
            ).fetchall()

    @staticmethod
    def get_role(role_id: int):
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM admin_roles WHERE id=?", (role_id,)
            ).fetchone()

    @staticmethod
    def create_role(
        role_code: str, role_name: str, role_type: str, description: str, menu_ids
    ):
        try:
            with get_connection() as conn:
                cur = conn.execute(
                    """INSERT INTO admin_roles(role_code, role_name, role_type, description)
                       VALUES(?, ?, ?, ?)""",
                    (role_code, role_name, role_type, description),
                )
                new_id = cur.lastrowid
                if new_id is None:
                    return False, "角色创建失败"
                AdminRepository._replace_role_menus(conn, new_id, menu_ids)
            return True, None
        except sqlite3.IntegrityError:
            return False, "角色编码已存在"

    @staticmethod
    def update_role(
        role_id: int,
        role_name: str,
        role_type: str,
        description: str,
        status: str,
        menu_ids,
    ):
        with get_connection() as conn:
            role = conn.execute(
                "SELECT is_system FROM admin_roles WHERE id=?", (role_id,)
            ).fetchone()
            if not role:
                return False, "角色不存在"
            if role["is_system"]:
                return False, "系统内置角色不允许修改"
            conn.execute(
                """UPDATE admin_roles
                   SET role_name=?, role_type=?, description=?, status=?,
                       updated_at=datetime('now')
                   WHERE id=?""",
                (role_name, role_type, description, status, role_id),
            )
            AdminRepository._replace_role_menus(conn, role_id, menu_ids)
        return True, None

    @staticmethod
    def delete_role(role_id: int):
        with get_connection() as conn:
            role = conn.execute(
                "SELECT is_system FROM admin_roles WHERE id=?", (role_id,)
            ).fetchone()
            if not role:
                return False, "角色不存在"
            if role["is_system"]:
                return False, "系统内置角色不允许删除"
            used = conn.execute(
                "SELECT count(*) FROM admin_users WHERE role_id=?", (role_id,)
            ).fetchone()[0]
            if used:
                return False, "该角色已被用户使用，不能删除"
            conn.execute("DELETE FROM admin_role_menus WHERE role_id=?", (role_id,))
            conn.execute("DELETE FROM admin_roles WHERE id=?", (role_id,))
        return True, None

    @staticmethod
    def list_menus(keyword: str = "", page: int = 1, per_page: int = PER_PAGE):
        where = ""
        params = []
        if keyword.strip():
            where = (
                "where menu_code like ? or menu_name like ? or ifnull(url, '') like ?"
            )
            params = [_like(keyword), _like(keyword), _like(keyword)]

        with get_connection() as conn:
            total = conn.execute(
                f"SELECT count(*) FROM admin_menus {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""SELECT * FROM admin_menus
                    {where}
                    ORDER BY sort_order ASC, id ASC
                    LIMIT ? OFFSET ?""",
                params + [per_page, _page_offset(page, per_page)],
            ).fetchall()
        return rows, total

    @staticmethod
    def list_all_menus():
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM admin_menus WHERE status='enabled' ORDER BY sort_order ASC, id ASC"
            ).fetchall()

    @staticmethod
    def get_menu(menu_id: int):
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM admin_menus WHERE id=?", (menu_id,)
            ).fetchone()

    @staticmethod
    def create_menu(
        menu_code: str,
        menu_name: str,
        icon: str,
        url: str,
        sort_order: int,
        parent_id: int = 0,
    ):
        try:
            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO admin_menus(parent_id, menu_code, menu_name, icon, url, sort_order)
                       VALUES(?, ?, ?, ?, ?, ?)""",
                    (parent_id, menu_code, menu_name, icon, url, sort_order),
                )
            return True, None
        except sqlite3.IntegrityError:
            return False, "功能编码已存在"

    @staticmethod
    def update_menu(
        menu_id: int,
        menu_name: str,
        icon: str,
        url: str,
        sort_order: int,
        status: str,
        parent_id: int = 0,
    ):
        with get_connection() as conn:
            conn.execute(
                """UPDATE admin_menus
                   SET parent_id=?, menu_name=?, icon=?, url=?, sort_order=?,
                       status=?, updated_at=datetime('now')
                   WHERE id=?""",
                (parent_id, menu_name, icon, url, sort_order, status, menu_id),
            )
        return True, None

    @staticmethod
    def delete_menu(menu_id: int):
        with get_connection() as conn:
            children = conn.execute(
                "SELECT count(*) FROM admin_menus WHERE parent_id=?", (menu_id,)
            ).fetchone()[0]
            if children:
                return False, "存在子功能，不能删除"
            conn.execute("DELETE FROM admin_role_menus WHERE menu_id=?", (menu_id,))
            conn.execute("DELETE FROM admin_menus WHERE id=?", (menu_id,))
        return True, None

    @staticmethod
    def get_role_menu_ids(role_id: int):
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT menu_id FROM admin_role_menus WHERE role_id=?", (role_id,)
            ).fetchall()
        return [row["menu_id"] for row in rows]

    @staticmethod
    def _replace_role_menus(conn, role_id: int, menu_ids):
        conn.execute("DELETE FROM admin_role_menus WHERE role_id=?", (role_id,))
        ids = [
            (role_id, int(menu_id)) for menu_id in menu_ids if str(menu_id).isdigit()
        ]
        if ids:
            conn.executemany(
                "INSERT OR IGNORE INTO admin_role_menus(role_id, menu_id) VALUES(?, ?)",
                ids,
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
                f"SELECT count(*) FROM admin_users au LEFT JOIN admin_roles ar ON ar.id=au.role_id {where}",
                params,
            ).fetchone()[0]
            rows = conn.execute(
                f"""SELECT au.id, au.username, au.display_name, au.role_id, au.is_super, au.status,
                           au.created_at, ar.role_name, ar.role_code
                    FROM admin_users au
                    LEFT JOIN admin_roles ar ON ar.id=au.role_id
                    {where}
                    ORDER BY au.is_super DESC, au.id ASC
                    LIMIT ? OFFSET ?""",
                params + [per_page, _page_offset(page, per_page)],
            ).fetchall()
        return rows, total

    @staticmethod
    def get_user(user_id: int):
        with get_connection() as conn:
            return conn.execute(
                "SELECT id, username, display_name, role_id, is_super, status FROM admin_users WHERE id=?",
                (user_id,),
            ).fetchone()

    @staticmethod
    def create_user(
        username: str, password: str, display_name: str, role_id: int, status: str
    ):
        if not password or len(password) < 8:
            return False, "密码长度不能少于8位"
        if username and username.lower() in password.lower():
            return False, "密码不能包含用户名"
        salt = secrets.token_bytes(16)
        try:
            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO admin_users(username, password_hash, salt, display_name, role_id, status)
                       VALUES(?, ?, ?, ?, ?, ?)""",
                    (
                        username,
                        hash_password(password, salt),
                        salt.hex(),
                        display_name,
                        role_id,
                        status,
                    ),
                )
            return True, None
        except sqlite3.IntegrityError:
            return False, "用户名已存在"

    @staticmethod
    def update_user(
        user_id: int, display_name: str, role_id: int, status: str, password: str = ""
    ):
        with get_connection() as conn:
            user = conn.execute(
                "SELECT username, is_super FROM admin_users WHERE id=?", (user_id,)
            ).fetchone()
            if not user:
                return False, "用户不存在"
            if user["username"] == "admin" and status != "enabled":
                return False, "admin 不允许禁用"
            if password:
                if len(password) < 8:
                    return False, "密码长度不能少于8位"
                salt = secrets.token_bytes(16)
                conn.execute(
                    """UPDATE admin_users
                       SET display_name=?, role_id=?, status=?, password_hash=?, salt=?,
                           updated_at=datetime('now')
                       WHERE id=?""",
                    (
                        display_name,
                        role_id,
                        status,
                        hash_password(password, salt),
                        salt.hex(),
                        user_id,
                    ),
                )
            else:
                conn.execute(
                    """UPDATE admin_users
                       SET display_name=?, role_id=?, status=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (display_name, role_id, status, user_id),
                )
        return True, None

    @staticmethod
    def get_admin_allowed_urls(admin_id: int) -> set[str]:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT DISTINCT am.url
                   FROM admin_users au
                   JOIN admin_role_menus arm ON arm.role_id = au.role_id
                   JOIN admin_menus am ON am.id = arm.menu_id
                   WHERE au.id = ? AND am.status = 'enabled'
                     AND am.url IS NOT NULL AND am.url <> ''""",
                (admin_id,),
            ).fetchall()
        return {row["url"] for row in rows}

    @staticmethod
    def delete_user(user_id: int):
        with get_connection() as conn:
            user = conn.execute(
                "SELECT username FROM admin_users WHERE id=?", (user_id,)
            ).fetchone()
            if not user:
                return False, "用户不存在"
            if user["username"] == "admin":
                return False, "admin 不允许删除"
            conn.execute("DELETE FROM admin_users WHERE id=?", (user_id,))
        return True, None
