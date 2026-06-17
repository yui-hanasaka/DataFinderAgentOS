import os
import re
import sqlite3
from pathlib import Path

from app.models.crypto import hash_password, new_salt


def _project_root() -> Path:
    return Path(
        os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
    )


DB_PATH = os.environ.get(
    "DATAFINDER_DB_PATH",
    os.path.join(_project_root(), "database", "app.db"),
)


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Table initialisers ──────────────────────────────────────────


def _init_users_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def _init_admin_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_roles(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_code TEXT NOT NULL UNIQUE,
            role_name TEXT NOT NULL,
            role_type TEXT NOT NULL DEFAULT 'manager',
            description TEXT,
            is_system INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'enabled',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            is_super INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'enabled',
            must_change_password INTEGER NOT NULL DEFAULT 0,
            last_login_at TEXT,
            failed_login_count INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT,
            FOREIGN KEY(role_id) REFERENCES admin_roles(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_menus(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL DEFAULT 0,
            menu_code TEXT NOT NULL UNIQUE,
            menu_name TEXT NOT NULL,
            icon TEXT,
            url TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'enabled',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_role_menus(
            role_id INTEGER NOT NULL,
            menu_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY(role_id, menu_id),
            FOREIGN KEY(role_id) REFERENCES admin_roles(id),
            FOREIGN KEY(menu_id) REFERENCES admin_menus(id)
        )
        """
    )


def _ensure_admin_role_columns(conn: sqlite3.Connection) -> None:
    columns = [
        row["name"] for row in conn.execute("PRAGMA table_info(admin_roles)").fetchall()
    ]
    if "role_type" not in columns:
        conn.execute(
            "ALTER TABLE admin_roles ADD COLUMN role_type TEXT NOT NULL DEFAULT 'manager'"
        )


def _ensure_admin_user_columns(conn: sqlite3.Connection) -> None:
    columns = [
        row["name"] for row in conn.execute("PRAGMA table_info(admin_users)").fetchall()
    ]
    for col, col_def in [
        ("must_change_password", "INTEGER NOT NULL DEFAULT 0"),
        ("last_login_at", "TEXT"),
        ("failed_login_count", "INTEGER NOT NULL DEFAULT 0"),
        ("locked_until", "TEXT"),
    ]:
        if col not in columns:
            conn.execute(f"ALTER TABLE admin_users ADD COLUMN {col} {col_def}")


def _seed_admin_data(conn: sqlite3.Connection) -> None:
    _ensure_admin_role_columns(conn)
    _ensure_admin_user_columns(conn)
    conn.execute(
        """
        INSERT OR IGNORE INTO admin_roles(role_code, role_name, role_type, description, is_system)
        VALUES('super_admin', '超级管理员', 'manager', '系统内置超级管理员角色，不允许删除和修改', 1)
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO admin_roles(role_code, role_name, role_type, description, is_system)
        VALUES('manager', '管理用户', 'manager', '后台管理侧普通管理角色，可按需分配菜单权限', 0)
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO admin_roles(role_code, role_name, role_type, description, is_system)
        VALUES('web_user', '普通用户', 'web_user', '前台用户侧访问角色', 1)
        """
    )
    conn.execute(
        "update admin_roles set role_type='manager' where role_code in ('super_admin', 'manager')"
    )
    conn.execute(
        "update admin_roles set role_type='web_user' where role_code='web_user'"
    )

    menus = [
        ("dashboard", "后台主页", "⌂", "/admin/home", 10),
        ("user_manage", "用户管理", "👤", "/admin/users", 20),
        ("role_manage", "角色管理", "🛡", "/admin/roles", 30),
        ("menu_manage", "功能管理", "▦", "/admin/menus", 40),
        ("model_engine", "模型引擎", "⚙", "/admin/models", 50),
        ("skill_store", "技能仓库", "◇", "/admin/skills", 60),
        ("digital_staff", "数字员工", "🤖", "/admin/employees", 70),
        ("watch_collect", "瞭望采集", "⌁", "/admin/watchtower", 80),
        ("data_warehouse", "数据仓库", "▣", "/admin/warehouse", 90),
        ("deep_collect", "深度采集", "⌬", "/admin/deep", 100),
        ("smart_qa", "智能问数", "⌕", "", 110),
        ("smart_screen", "数智大屏", "◈", "/admin/screen", 120),
        ("sys_settings", "系统设置", "⚙", "/admin/settings", 140),
        ("api_keys", "接口管理", "🔌", "/admin/apis", 150),
        ("session_mgr", "会话管理", "💬", "/admin/sessions", 160),
        ("permissions", "权限管理", "🔐", "/admin/permissions", 170),
        ("digital_twin", "数字孪生", "🌐", "/admin/digital-twin", 180),
        ("screen_config", "大屏配置", "📊", "/admin/screen/config", 190),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO admin_menus(menu_code, menu_name, icon, url, sort_order)
        VALUES(?, ?, ?, ?, ?)
        """,
        menus,
    )

    role = conn.execute(
        "select id from admin_roles where role_code='super_admin'"
    ).fetchone()
    if role:
        menu_rows = conn.execute("select id from admin_menus").fetchall()
        conn.executemany(
            "INSERT OR IGNORE INTO admin_role_menus(role_id, menu_id) VALUES(?, ?)",
            [(role["id"], row["id"]) for row in menu_rows],
        )

    admin_exists = conn.execute(
        "select id from admin_users where username='admin'"
    ).fetchone()
    if not admin_exists and role:
        salt = new_salt()
        dev = os.environ.get("DEV", "").lower() in ("1", "true", "yes")
        default_pw = os.environ.get("ADMIN_INITIAL_PASSWORD", "")
        if not default_pw and not dev:
            dev = True  # auto-dev: no ADMIN_INITIAL_PASSWORD set
        if not default_pw and dev:
            default_pw = "admin888"
        if not default_pw:
            raise SystemExit(
                "FATAL: No admin user exists and ADMIN_INITIAL_PASSWORD is not set."
                " Set the environment variable and restart."
            )
        must_change = (
            1
            if default_pw == "admin888" or not os.environ.get("ADMIN_INITIAL_PASSWORD")
            else 0
        )
        conn.execute(
            """
            INSERT INTO admin_users(username, password_hash, salt, display_name, role_id, is_super, must_change_password)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "admin",
                hash_password(default_pw, salt),
                salt.hex(),
                "超级管理员",
                role["id"],
                1,
                must_change,
            ),
        )


def _init_model_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_models(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            model_id TEXT NOT NULL,
            model_type TEXT NOT NULL DEFAULT 'text',
            base_url TEXT NOT NULL,
            api_key TEXT NOT NULL,
            temperature REAL NOT NULL DEFAULT 0.7,
            max_tokens INTEGER NOT NULL DEFAULT 1024,
            system_prompt TEXT,
            support_stream INTEGER NOT NULL DEFAULT 1,
            support_think INTEGER NOT NULL DEFAULT 0,
            is_default INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'enabled',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_model_usage(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(model_id) REFERENCES ai_models(id)
        )
        """
    )


def _init_business_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS digital_employees(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            avatar TEXT NOT NULL DEFAULT '🤖',
            model_id INTEGER NOT NULL DEFAULT 0,
            system_prompt TEXT,
            skills TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'enabled',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS skills(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            skill_type TEXT NOT NULL DEFAULT 'builtin',
            config_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'enabled',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS chat_sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 0,
            employee_id INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL DEFAULT '新对话',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS chat_messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            content TEXT NOT NULL,
            skill_meta TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
        );
        CREATE TABLE IF NOT EXISTS watchtower_sources(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'rss',
            url TEXT NOT NULL,
            url_template TEXT,
            request_headers TEXT NOT NULL DEFAULT '',
            config_json TEXT NOT NULL DEFAULT '{}',
            fetch_interval INTEGER NOT NULL DEFAULT 60,
            status TEXT NOT NULL DEFAULT 'enabled',
            last_fetched TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS watchtower_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            url TEXT,
            sentiment TEXT,
            risk INTEGER NOT NULL DEFAULT 0,
            published_at TEXT,
            is_deep_collected INTEGER NOT NULL DEFAULT 0,
            deep_task_id INTEGER DEFAULT NULL,
            deep_collected_at TEXT DEFAULT NULL,
            summary TEXT,
            keywords TEXT NOT NULL DEFAULT '[]',
            raw_json TEXT NOT NULL DEFAULT '{}',
            collected_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT,
            FOREIGN KEY(source_id) REFERENCES watchtower_sources(id)
        );
        CREATE TABLE IF NOT EXISTS deep_tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            target_url TEXT NOT NULL,
            depth INTEGER NOT NULL DEFAULT 1,
            schedule TEXT,
            status TEXT NOT NULL DEFAULT 'idle',
            target_item_ids TEXT NOT NULL DEFAULT '[]',
            progress INTEGER NOT NULL DEFAULT 0,
            total_items INTEGER NOT NULL DEFAULT 0,
            completed_items INTEGER NOT NULL DEFAULT 0,
            failed_items INTEGER NOT NULL DEFAULT 0,
            logs TEXT NOT NULL DEFAULT '[]',
            started_at TEXT,
            finished_at TEXT,
            error_message TEXT,
            last_run TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS deep_contents(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            task_id INTEGER,
            title TEXT,
            url TEXT,
            markdown TEXT NOT NULL DEFAULT '',
            plain_text TEXT NOT NULL DEFAULT '',
            summary TEXT,
            keywords TEXT NOT NULL DEFAULT '[]',
            sentiment TEXT,
            risk INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(item_id) REFERENCES watchtower_items(id) ON DELETE CASCADE,
            FOREIGN KEY(task_id) REFERENCES deep_tasks(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS ask_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            query TEXT NOT NULL,
            generated_sql TEXT,
            result_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'ok',
            error_code TEXT,
            model_id INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS api_keys(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            api_type TEXT NOT NULL DEFAULT 'weather',
            endpoint TEXT,
            api_key TEXT,
            status TEXT NOT NULL DEFAULT 'enabled',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS data_warehouse(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sql_query TEXT NOT NULL,
            description TEXT,
            category TEXT NOT NULL DEFAULT '默认',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sys_settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS screen_configs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            screen_type TEXT NOT NULL DEFAULT 'smart',
            layout_json TEXT NOT NULL DEFAULT '{}',
            is_public INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'enabled',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS screen_widgets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_id INTEGER NOT NULL,
            widget_type TEXT NOT NULL,
            title TEXT NOT NULL,
            data_query TEXT,
            settings_json TEXT NOT NULL DEFAULT '{}',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT,
            FOREIGN KEY(config_id) REFERENCES screen_configs(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS digital_twin_scenes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            scene_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'enabled',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS digital_twin_models(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            model_type TEXT NOT NULL DEFAULT 'primitive',
            asset_url TEXT,
            transform_json TEXT NOT NULL DEFAULT '{}',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT,
            FOREIGN KEY(scene_id) REFERENCES digital_twin_scenes(id) ON DELETE CASCADE
        );
    """)


def _seed_business_data(conn: sqlite3.Connection) -> None:
    builtin_skills = [
        ("weather", "天气查询", "builtin", '{"prefix": "@weather"}'),
        ("music", "音乐播放", "builtin", '{"prefix": "@music"}'),
        ("campus", "西师妹校园助手", "builtin", '{"prefix": "@西师妹"}'),
        ("websearch", "网络搜索", "builtin", '{"prefix": "\\\\search"}'),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO skills(code, name, skill_type, config_json) VALUES(?,?,?,?)",
        builtin_skills,
    )
    default_employee = conn.execute(
        "SELECT id FROM digital_employees WHERE name='智能助手'"
    ).fetchone()
    if not default_employee:
        conn.execute(
            """INSERT INTO digital_employees(name, avatar, system_prompt, skills)
               VALUES('智能助手', '🤖', '你是一个智能助手，请以专业、友善的方式回答用户问题。',
                      '["weather","music","campus","websearch"]')"""
        )
    conn.execute(
        "INSERT OR IGNORE INTO sys_settings(key, value) VALUES('db_type', 'sqlite')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO sys_settings(key, value) VALUES('site_name', 'DataFinder AgentOS')"
    )
    # seed a demo front-end user (demo / demo123) for quick testing
    demo_exists = conn.execute("SELECT id FROM users WHERE username='demo'").fetchone()
    if not demo_exists:
        salt = new_salt()
        conn.execute(
            "INSERT INTO users(username, password_hash, salt) VALUES(?,?,?)",
            ("demo", hash_password("demo123", salt), salt.hex()),
        )


# ── Migration runner ────────────────────────────────────────────


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations(
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def _migrate(conn: sqlite3.Connection, version: str, sql: str) -> None:
    cur = conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (version,))
    if cur.fetchone():
        return
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            # Use regex to extract ALTER TABLE <t> ADD [COLUMN] <c> ...
            m = re.match(
                r"ALTER\s+TABLE\s+(\S+)\s+ADD\s+(?:COLUMN\s+)?(\S+)",
                stmt,
                re.IGNORECASE,
            )
            if m:
                table = m.group(1)
                col = m.group(2)
                existing = [
                    r["name"]
                    for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
                ]
                if col not in existing:
                    conn.execute(stmt)
            else:
                conn.execute(stmt)
        except Exception as e:
            print(
                f"[migration:{version}] skipped statement due to error: {e}\n"
                f"  SQL: {stmt}"
            )
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version) VALUES(?)", (version,)
    )


def _run_migrations(conn: sqlite3.Connection) -> None:
    _ensure_schema_migrations(conn)

    # v1 — ensure foreign-key columns on existing tables
    _migrate(
        conn,
        "v1_watchtower_item_deep_tracking",
        """
        ALTER TABLE watchtower_items ADD COLUMN is_deep_collected INTEGER DEFAULT 0;
        ALTER TABLE watchtower_items ADD COLUMN deep_task_id INTEGER DEFAULT NULL;
        ALTER TABLE watchtower_items ADD COLUMN deep_collected_at TEXT DEFAULT NULL;
        """,
    )
    _migrate(
        conn,
        "v1_deep_task_progress",
        """
        ALTER TABLE deep_tasks ADD COLUMN progress INTEGER DEFAULT 0;
        ALTER TABLE deep_tasks ADD COLUMN total_items INTEGER DEFAULT 0;
        ALTER TABLE deep_tasks ADD COLUMN completed_items INTEGER DEFAULT 0;
        ALTER TABLE deep_tasks ADD COLUMN failed_items INTEGER DEFAULT 0;
        ALTER TABLE deep_tasks ADD COLUMN logs TEXT DEFAULT '[]';
        """,
    )
    _migrate(
        conn,
        "v1_admin_user_security",
        """
        ALTER TABLE admin_users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE admin_users ADD COLUMN last_login_at TEXT;
        ALTER TABLE admin_users ADD COLUMN failed_login_count INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE admin_users ADD COLUMN locked_until TEXT;
        """,
    )
    _migrate(
        conn,
        "v1_watchtower_source_extended",
        """
        ALTER TABLE watchtower_sources ADD COLUMN url_template TEXT;
        ALTER TABLE watchtower_sources ADD COLUMN request_headers TEXT NOT NULL DEFAULT '';
        ALTER TABLE watchtower_sources ADD COLUMN config_json TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE watchtower_sources ADD COLUMN updated_at TEXT;
        """,
    )
    _migrate(
        conn,
        "v1_watchtower_item_extended",
        """
        ALTER TABLE watchtower_items ADD COLUMN summary TEXT;
        ALTER TABLE watchtower_items ADD COLUMN keywords TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE watchtower_items ADD COLUMN raw_json TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE watchtower_items ADD COLUMN collected_at TEXT;
        ALTER TABLE watchtower_items ADD COLUMN updated_at TEXT;
        """,
    )
    _migrate(
        conn,
        "v1_deep_tasks_extended",
        """
        ALTER TABLE deep_tasks ADD COLUMN target_item_ids TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE deep_tasks ADD COLUMN started_at TEXT;
        ALTER TABLE deep_tasks ADD COLUMN finished_at TEXT;
        ALTER TABLE deep_tasks ADD COLUMN error_message TEXT;
        """,
    )
    _migrate(
        conn,
        "v1_api_keys_updated_at",
        "ALTER TABLE api_keys ADD COLUMN updated_at TEXT;",
    )
    _migrate(
        conn,
        "v2_chat_session_model_id",
        "ALTER TABLE chat_sessions ADD COLUMN model_id INTEGER DEFAULT 0;",
    )

    # Indexes (idempotent)
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id, updated_at, id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_watchtower_items_source ON watchtower_items(source_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_watchtower_items_url ON watchtower_items(url)",
        "CREATE INDEX IF NOT EXISTS idx_ai_model_usage_model ON ai_model_usage(model_id)",
        "CREATE INDEX IF NOT EXISTS idx_api_keys_type ON api_keys(api_type, status)",
        "CREATE INDEX IF NOT EXISTS idx_deep_contents_item ON deep_contents(item_id)",
        "CREATE INDEX IF NOT EXISTS idx_deep_tasks_status ON deep_tasks(status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_ask_history_user ON ask_history(user_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_screen_widgets_config ON screen_widgets(config_id, sort_order)",
        "CREATE INDEX IF NOT EXISTS idx_digital_twin_models_scene ON digital_twin_models(scene_id)",
        "CREATE INDEX IF NOT EXISTS idx_admin_role_menus_menu ON admin_role_menus(menu_id)",
        "CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status)",
        "CREATE INDEX IF NOT EXISTS idx_digital_employees_status ON digital_employees(status)",
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_employee ON chat_sessions(employee_id)",
        "CREATE INDEX IF NOT EXISTS idx_admin_menus_url ON admin_menus(url)",
    ]
    for sql in indexes:
        conn.execute(sql)


def init_db() -> None:
    with get_connection() as conn:
        _init_users_table(conn)
        _init_admin_tables(conn)
        _seed_admin_data(conn)
        _init_model_tables(conn)
        _init_business_tables(conn)
        _seed_business_data(conn)
        _run_migrations(conn)
