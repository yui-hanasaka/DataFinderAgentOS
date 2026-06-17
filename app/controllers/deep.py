from app.controllers.admin import AdminBaseHandler
from app.models.db import get_connection

PER_PAGE = 20


class AdminDeepHandler(AdminBaseHandler):
    def get(self):
        page = self._page()
        with get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM deep_tasks").fetchone()[0]
            offset = (max(page, 1) - 1) * PER_PAGE
            tasks = conn.execute(
                "SELECT * FROM deep_tasks ORDER BY id DESC LIMIT ? OFFSET ?",
                (PER_PAGE, offset),
            ).fetchall()
        self.render(
            "admin/deep.html",
            title="深度采集",
            username=self.current_user,
            tasks=tasks,
            total=total,
            page=page,
            per_page=PER_PAGE,
            msg=self._message(),
        )

    def post(self):
        action = self.get_body_argument("action", "")
        task_id = self.get_body_argument("id", "")
        if action == "delete" and task_id.isdigit():
            with get_connection() as conn:
                conn.execute("DELETE FROM deep_tasks WHERE id=?", (int(task_id),))
            return self._redirect_with_message("/admin/deep", "任务已删除")
        if action == "run" and task_id.isdigit():
            with get_connection() as conn:
                conn.execute(
                    "UPDATE deep_tasks SET status='running', last_run=datetime('now') WHERE id=?",
                    (int(task_id),),
                )
            return self._redirect_with_message("/admin/deep", "任务已启动")
        name = self.get_body_argument("name", "").strip()
        target_url = self.get_body_argument("target_url", "").strip()
        depth = int(self.get_body_argument("depth", "1") or 1)
        schedule = self.get_body_argument("schedule", "").strip()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO deep_tasks(name, target_url, depth, schedule) VALUES(?,?,?,?)",
                (name, target_url, depth, schedule),
            )
        self._redirect_with_message("/admin/deep", "任务已新增")
