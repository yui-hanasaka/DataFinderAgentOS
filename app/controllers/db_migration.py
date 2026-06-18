"""Database migration admin handler."""

from app.controllers.admin import AdminBaseHandler
from app.models.db import _load_mysql_params, _sqlite_raw_connect
from app.models.db_migration import DatabaseMigrator
from app.models.db_switcher import (
    get_migration_status,
    switch_to_mysql,
    switch_to_sqlite,
)


class AdminDbMigrationHandler(AdminBaseHandler):
    def get(self) -> None:
        status = get_migration_status()
        with _sqlite_raw_connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master"
                " WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            table_stats: list[dict] = []
            for t in tables:
                cnt = conn.execute(
                    f"SELECT COUNT(*) as n FROM [{t['name']}]"
                ).fetchone()["n"]
                table_stats.append({"name": t["name"], "rows": cnt})

        self.render(
            "admin/db_migration.html",
            title="数据库迁移",
            username=self.current_user,
            status=status,
            table_stats=table_stats,
            msg=self._message(),
        )

    def post(self) -> None:
        action = self.get_body_argument("action", "")
        if action == "export_schema":
            return self._export_schema()
        if action == "migrate_data":
            return self._migrate_data()
        if action == "switch_to_mysql":
            return self._switch_to_mysql()
        if action == "switch_to_sqlite":
            return self._switch_to_sqlite()
        self.set_status(400)
        self.write({"error": "未知操作"})

    def _export_schema(self) -> None:
        ddls = DatabaseMigrator.export_schema_to_mysql()
        self.set_header("Content-Type", "text/plain; charset=utf-8")
        self.write("\n\n".join(ddls))

    async def _migrate_data(self) -> None:
        params = _load_mysql_params()
        if not params.get("host"):
            self.set_status(400)
            self.write({"error": "MySQL未配置，请先在系统设置中配置"})
            return
        results = await DatabaseMigrator.migrate_all_tables(params)
        total_s = sum(v[0] for v in results.values())
        total_f = sum(v[1] for v in results.values())
        self.write({"ok": True, "success": total_s, "failed": total_f})

    def _switch_to_mysql(self) -> None:
        params = _load_mysql_params()
        ok, msg = switch_to_mysql(params)
        if ok:
            self.write({"ok": True, "message": msg})
        else:
            self.set_status(500)
            self.write({"error": msg})

    def _switch_to_sqlite(self) -> None:
        ok, msg = switch_to_sqlite()
        if ok:
            self.write({"ok": True, "message": msg})
        else:
            self.set_status(500)
            self.write({"error": msg})
