from app.controllers.admin import AdminBaseHandler
from app.models.db import get_connection
from app.models.errors import log_error
from app.models.rate_limit import check_rate_limit
from app.models.secrets_store import decrypt, mask
from app.models.validators import parse_int


class AdminSettingsHandler(AdminBaseHandler):
    def _load_settings(self) -> dict[str, str]:
        with get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM sys_settings").fetchall()
        settings = {r["key"]: r["value"] for r in rows}
        # Mask sensitive values for display
        if "mysql_password" in settings:
            settings["mysql_password"] = mask(
                decrypt(settings["mysql_password"])
                if settings["mysql_password"]
                else ""
            )
        return settings

    def _save(self, key: str, value: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sys_settings(key,value,updated_at) VALUES(?,?,datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, value),
            )

    def get(self) -> None:
        settings = self._load_settings()
        self.render(
            "admin/settings.html",
            title="系统设置",
            username=self.current_user,
            settings=settings,
            msg=self._message(),
        )

    def post(self) -> None:
        if not check_rate_limit(f"admin_settings:{self.current_user}", 10, 60):
            self.set_status(429)
            return self.write({"error": "请求过于频繁，请稍后再试"})

        action = self.get_body_argument("action", "")
        if action == "test_db":
            self.set_header("Content-Type", "application/json")
            db_type = self.get_body_argument("db_type", "sqlite")
            if db_type == "sqlite":
                return self.write({"ok": True, "msg": "SQLite 连接正常"})
            try:
                import pymysql

                host = self.get_body_argument("mysql_host", "127.0.0.1")
                port = parse_int(
                    self.get_body_argument("mysql_port", "3306"),
                    3306,
                    min_value=1,
                    max_value=65535,
                )
                user = self.get_body_argument("mysql_user", "")
                password = self.get_body_argument("mysql_password", "")
                database = self.get_body_argument("mysql_database", "")
                conn = pymysql.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=database,
                    connect_timeout=3,
                )
                conn.close()

                # Also verify DDL can be created
                from app.models.db_switcher import DatabaseSwitcher

                switcher = DatabaseSwitcher(
                    "mysql",
                    {
                        "host": host,
                        "port": port,
                        "user": user,
                        "password": password,
                        "database": database,
                    },
                )
                switcher.preflight()
                return self.write({"ok": True, "msg": "MySQL 连接成功，建表验证通过"})
            except Exception as e:
                log_error("MySQL 连接测试失败", e)
                return self.write({"ok": False, "msg": f"MySQL 连接失败: {e}"})

        # ── Save settings (with potential DB switch) ──────────

        site_name = self.get_body_argument("site_name", "DataFinder AgentOS").strip()
        db_type = self.get_body_argument("db_type", "sqlite")

        # Save basic settings first (always to current active DB)
        self._save("site_name", site_name)

        # Check if db_type changed
        import app.models.db as db_module

        old_db_type = db_module._active_db_type
        if db_type != old_db_type:
            # Switching databases
            from app.models.db_switcher import DatabaseSwitcher, DatabaseSwitchError
            from app.models.secrets_store import encrypt

            if db_type == "mysql":
                params = {
                    "host": self.get_body_argument("mysql_host", "127.0.0.1"),
                    "port": parse_int(
                        self.get_body_argument("mysql_port", "3306"),
                        3306,
                        min_value=1,
                        max_value=65535,
                    ),
                    "user": self.get_body_argument("mysql_user", ""),
                    "password": self.get_body_argument("mysql_password", ""),
                    "database": self.get_body_argument("mysql_database", ""),
                }
            else:
                params = {}

            try:
                switcher = DatabaseSwitcher(db_type, params)
                switcher.run()
            except DatabaseSwitchError as e:
                log_error("数据库切换失败", e)
                self._redirect_with_message("/admin/settings", f"数据库切换失败: {e}")
                return
        else:
            # Same db_type — just save MySQL params (don't switch)
            if db_type == "mysql":
                from app.models.secrets_store import encrypt

                for k in (
                    "mysql_host",
                    "mysql_port",
                    "mysql_user",
                    "mysql_password",
                    "mysql_database",
                ):
                    val = self.get_body_argument(k, "")
                    if k == "mysql_password" and val:
                        # Guard: do NOT overwrite real password with masked value
                        if "****" in val and len(val) < 20:
                            continue
                        val = encrypt(val)
                    elif k == "mysql_password" and not val:
                        continue
                    self._save(k, val)

            self._save("db_type", db_type)

        self._redirect_with_message("/admin/settings", "设置已保存")
