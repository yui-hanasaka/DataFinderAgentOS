import json
from app.controllers.admin import AdminBaseHandler
from app.models.db import get_connection

class AdminSettingsHandler(AdminBaseHandler):
    def _load_settings(self):
        with get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM sys_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def _save(self, key, value):
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sys_settings(key,value,updated_at) VALUES(?,?,datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, value)
            )

    def get(self):
        settings = self._load_settings()
        self.render("admin/settings.html", title="系统设置", username=self.current_user,
                    settings=settings, msg=self._message())

    def post(self):
        action = self.get_body_argument("action", "")
        if action == "test_db":
            self.set_header("Content-Type", "application/json")
            db_type = self.get_body_argument("db_type", "sqlite")
            if db_type == "sqlite":
                return self.write({"ok": True, "msg": "SQLite 连接正常"})
            try:
                import pymysql
                host = self.get_body_argument("mysql_host", "127.0.0.1")
                port = int(self.get_body_argument("mysql_port", "3306") or 3306)
                user = self.get_body_argument("mysql_user", "")
                password = self.get_body_argument("mysql_password", "")
                database = self.get_body_argument("mysql_database", "")
                conn = pymysql.connect(host=host, port=port, user=user, password=password, database=database, connect_timeout=3)
                conn.close()
                return self.write({"ok": True, "msg": "MySQL 连接成功"})
            except Exception as e:
                return self.write({"ok": False, "msg": str(e)})

        site_name = self.get_body_argument("site_name", "DataFinder AgentOS").strip()
        db_type = self.get_body_argument("db_type", "sqlite")
        self._save("site_name", site_name)
        self._save("db_type", db_type)
        if db_type == "mysql":
            for k in ("mysql_host", "mysql_port", "mysql_user", "mysql_password", "mysql_database"):
                self._save(k, self.get_body_argument(k, ""))
        self._redirect_with_message("/admin/settings", "设置已保存")
