import sqlite3

from app.models.db import get_connection
from app.models.secrets_store import encrypt, mask


class ApiKeyRepository:
    @staticmethod
    def list_keys(keyword: str = "", page: int = 1) -> tuple[list[sqlite3.Row], int]:
        per_page = 20
        offset = (page - 1) * per_page
        like = f"%{keyword}%"
        where = "WHERE name LIKE ? OR api_type LIKE ?" if keyword else ""
        params = [like, like] if keyword else []
        with get_connection() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM api_keys {where}", params
                ).fetchone()[0]
            )
            rows = conn.execute(
                f"SELECT * FROM api_keys {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                params + [per_page, offset],
            ).fetchall()
        return rows, total

    @staticmethod
    def get_key(key_id: int) -> sqlite3.Row | None:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM api_keys WHERE id=?", (key_id,)
            ).fetchone()

    @staticmethod
    def create_key(data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            api_key_val = str(data.get("api_key", ""))
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO api_keys(name, api_type, endpoint, api_key, status)"
                    " VALUES(?,?,?,?,?)",
                    (
                        data["name"],
                        data["api_type"],
                        data.get("endpoint", ""),
                        encrypt(api_key_val) if api_key_val else "",
                        data["status"],
                    ),
                )
            return True, None
        except sqlite3.IntegrityError as e:
            return False, str(e)

    @staticmethod
    def update_key(key_id: int, data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            api_key_val = str(data.get("api_key", ""))
            api_key_save = encrypt(api_key_val) if api_key_val else ""
            if not api_key_val:
                with get_connection() as conn:
                    existing = conn.execute(
                        "SELECT api_key FROM api_keys WHERE id=?", (key_id,)
                    ).fetchone()
                    api_key_save = existing["api_key"] if existing else ""
            with get_connection() as conn:
                conn.execute(
                    "UPDATE api_keys SET name=?, api_type=?, endpoint=?,"
                    " api_key=?, status=?, updated_at=datetime('now')"
                    " WHERE id=?",
                    (
                        data["name"],
                        data["api_type"],
                        data.get("endpoint", ""),
                        api_key_save,
                        data["status"],
                        key_id,
                    ),
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_key(key_id: int) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM api_keys WHERE id=?", (key_id,))
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def mask_key(raw: str) -> str:
        return mask(raw)
