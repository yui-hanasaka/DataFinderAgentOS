import sqlite3

from app.models.db import get_connection
from app.models.errors import log_error


class DigitalTwinRepository:
    # ── Scenes ──

    @staticmethod
    def list_scenes() -> list[sqlite3.Row]:
        with get_connection() as conn:
            return conn.execute(
                """SELECT s.*,
                          (SELECT COUNT(*) FROM digital_twin_models m WHERE m.scene_id = s.id) AS model_count
                   FROM digital_twin_scenes s
                   ORDER BY s.id DESC"""
            ).fetchall()

    @staticmethod
    def get_scene(scene_id: int) -> sqlite3.Row | None:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM digital_twin_scenes WHERE id=?",
                (scene_id,),
            ).fetchone()

    @staticmethod
    def create_scene(data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO digital_twin_scenes(name, description, scene_json, status) VALUES(?,?,?,?)",
                    (
                        data["name"],
                        data.get("description", ""),
                        data.get("scene_json", "{}"),
                        data.get("status", "enabled"),
                    ),
                )
            return True, None
        except Exception as e:
            log_error("创建数字孪生场景失败", e)
            return False, str(e)

    @staticmethod
    def update_scene(scene_id: int, data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    """UPDATE digital_twin_scenes
                       SET name=?, description=?, scene_json=?, status=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (
                        data["name"],
                        data.get("description", ""),
                        data.get("scene_json", "{}"),
                        data.get("status", "enabled"),
                        scene_id,
                    ),
                )
            return True, None
        except Exception as e:
            log_error("更新数字孪生场景失败", e)
            return False, str(e)

    @staticmethod
    def delete_scene(scene_id: int) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM digital_twin_scenes WHERE id=?", (scene_id,))
            return True, None
        except Exception as e:
            log_error("删除数字孪生场景失败", e)
            return False, str(e)

    # ── Models ──

    @staticmethod
    def list_models(scene_id: int) -> list[sqlite3.Row]:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM digital_twin_models WHERE scene_id=? ORDER BY id ASC",
                (scene_id,),
            ).fetchall()

    @staticmethod
    def get_model(model_id: int) -> sqlite3.Row | None:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM digital_twin_models WHERE id=?",
                (model_id,),
            ).fetchone()

    @staticmethod
    def create_model(data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO digital_twin_models(scene_id, name, model_type, asset_url, transform_json, metadata_json)
                       VALUES(?,?,?,?,?,?)""",
                    (
                        data["scene_id"],
                        data["name"],
                        data.get("model_type", "primitive"),
                        data.get("asset_url", ""),
                        data.get("transform_json", "{}"),
                        data.get("metadata_json", "{}"),
                    ),
                )
            return True, None
        except Exception as e:
            log_error("创建数字孪生模型失败", e)
            return False, str(e)

    @staticmethod
    def update_model(model_id: int, data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    """UPDATE digital_twin_models
                       SET name=?, model_type=?, asset_url=?, transform_json=?, metadata_json=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (
                        data["name"],
                        data.get("model_type", "primitive"),
                        data.get("asset_url", ""),
                        data.get("transform_json", "{}"),
                        data.get("metadata_json", "{}"),
                        model_id,
                    ),
                )
            return True, None
        except Exception as e:
            log_error("更新数字孪生模型失败", e)
            return False, str(e)

    @staticmethod
    def delete_model(model_id: int) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM digital_twin_models WHERE id=?", (model_id,))
            return True, None
        except Exception as e:
            log_error("删除数字孪生模型失败", e)
            return False, str(e)
