import hashlib
import os
import secrets
import sqlite3


def _project_root():
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
    )


DB_PATH = os.path.join(_project_root(), "database", "app.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return dk.hex()


def _init_users_table(conn):
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


def _init_admin_tables(conn):
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


def _ensure_admin_role_columns(conn):
    columns = [
        row["name"] for row in conn.execute("PRAGMA table_info(admin_roles)").fetchall()
    ]
    if "role_type" not in columns:
        conn.execute(
            "ALTER TABLE admin_roles ADD COLUMN role_type TEXT NOT NULL DEFAULT 'manager'"
        )


def _seed_admin_data(conn):
    _ensure_admin_role_columns(conn)
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
        ("user_manage", "用户管理", "👤", "", 20),
        ("role_manage", "角色管理", "🛡", "", 30),
        ("menu_manage", "功能管理", "▦", "", 40),
        ("model_engine", "模型引擎", "⚙", "", 50),
        ("skill_store", "技能仓库", "◇", "", 60),
        ("digital_staff", "数字员工", "🤖", "", 70),
        ("watch_collect", "瞭望采集", "⌁", "", 80),
        ("data_warehouse", "数据仓库", "▣", "", 90),
        ("deep_collect", "深度采集", "⌬", "", 100),
        ("smart_qa", "智能问数", "⌕", "", 110),
        ("smart_screen", "智能大屏", "◈", "", 120),
    ]
    conn.executemany(
        """
		INSERT OR IGNORE INTO admin_menus(menu_code, menu_name, icon, url, sort_order)
		VALUES(?, ?, ?, ?, ?)
		""",
        menus,
    )
    conn.execute(
        "update admin_menus set url='/admin/users' where menu_code='user_manage'"
    )
    conn.execute(
        "update admin_menus set url='/admin/roles' where menu_code='role_manage'"
    )
    conn.execute(
        "update admin_menus set url='/admin/menus' where menu_code='menu_manage'"
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
        salt = secrets.token_bytes(16)
        conn.execute(
            """
			INSERT INTO admin_users(username, password_hash, salt, display_name, role_id, is_super)
			VALUES(?, ?, ?, ?, ?, ?)
			""",
            (
                "admin",
                _hash_password("admin888", salt),
                salt.hex(),
                "超级管理员",
                role["id"],
                1,
            ),
        )


def _init_model_tables(conn):
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


def _init_business_tables(conn):
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
			fetch_interval INTEGER NOT NULL DEFAULT 60,
			status TEXT NOT NULL DEFAULT 'enabled',
			last_fetched TEXT,
			created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
			created_at TEXT NOT NULL DEFAULT (datetime('now')),
			FOREIGN KEY(source_id) REFERENCES watchtower_sources(id)
		);
		CREATE TABLE IF NOT EXISTS deep_tasks(
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			name TEXT NOT NULL,
			target_url TEXT NOT NULL,
			depth INTEGER NOT NULL DEFAULT 1,
			schedule TEXT,
			status TEXT NOT NULL DEFAULT 'idle',
			last_run TEXT,
			created_at TEXT NOT NULL DEFAULT (datetime('now'))
		);
		CREATE TABLE IF NOT EXISTS api_keys(
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			name TEXT NOT NULL,
			api_type TEXT NOT NULL DEFAULT 'weather',
			endpoint TEXT,
			api_key TEXT,
			status TEXT NOT NULL DEFAULT 'enabled',
			created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
	""")


def _seed_business_data(conn):
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
        salt = secrets.token_bytes(16)
        conn.execute(
            "INSERT INTO users(username, password_hash, salt) VALUES(?,?,?)",
            ("demo", _hash_password("demo123", salt), salt.hex()),
        )


def _migrate_watchtower_items():
    """扩展watchtower_items表以支持深度采集追踪"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 检查列是否已存在
        cursor.execute("PRAGMA table_info(watchtower_items)")
        existing_columns = [row[1] for row in cursor.fetchall()]

        if "is_deep_collected" not in existing_columns:
            cursor.execute(
                "ALTER TABLE watchtower_items ADD COLUMN is_deep_collected INTEGER DEFAULT 0"
            )

        if "deep_task_id" not in existing_columns:
            cursor.execute(
                "ALTER TABLE watchtower_items ADD COLUMN deep_task_id INTEGER DEFAULT NULL"
            )

        if "deep_collected_at" not in existing_columns:
            cursor.execute(
                "ALTER TABLE watchtower_items ADD COLUMN deep_collected_at TEXT DEFAULT NULL"
            )

        conn.commit()


def _migrate_deep_tasks():
    """扩展deep_tasks表以支持进度追踪"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(deep_tasks)")
        existing_columns = [row[1] for row in cursor.fetchall()]

        if "progress" not in existing_columns:
            cursor.execute(
                "ALTER TABLE deep_tasks ADD COLUMN progress INTEGER DEFAULT 0"
            )

        if "total_items" not in existing_columns:
            cursor.execute(
                "ALTER TABLE deep_tasks ADD COLUMN total_items INTEGER DEFAULT 0"
            )

        if "completed_items" not in existing_columns:
            cursor.execute(
                "ALTER TABLE deep_tasks ADD COLUMN completed_items INTEGER DEFAULT 0"
            )

        if "failed_items" not in existing_columns:
            cursor.execute(
                "ALTER TABLE deep_tasks ADD COLUMN failed_items INTEGER DEFAULT 0"
            )

        if "logs" not in existing_columns:
            cursor.execute("ALTER TABLE deep_tasks ADD COLUMN logs TEXT DEFAULT '[]'")

        conn.commit()


def init_db():
    with get_connection() as conn:
        _init_users_table(conn)
        _init_admin_tables(conn)
        _seed_admin_data(conn)
        _init_model_tables(conn)
        _init_business_tables(conn)
        _seed_business_data(conn)

    # 执行迁移
    _migrate_watchtower_items()
    _migrate_deep_tasks()
