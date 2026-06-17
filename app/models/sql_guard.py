import re

# Tables that the AI ask endpoint must never read
_DENIED_TABLES: set[str] = {
    "users",
    "admin_users",
    "admin_roles",
    "admin_role_menus",
    "admin_menus",
    "api_keys",
    "sys_settings",
    "ai_models",
    "ai_model_usage",
    "sqlite_master",
    "sqlite_schema",
    "schema_migrations",
    "deep_tasks",
    "ask_history",
    "screen_configs",
    "screen_widgets",
    "digital_twin_scenes",
    "digital_twin_models",
}

# Tables that the AI ask endpoint is allowed to query
_ALLOWED_TABLES: set[str] = {
    "watchtower_items",
    "watchtower_sources",
    "deep_contents",
    "digital_employees",
    "skills",
}


def validate_select_sql(sql: str) -> tuple[bool, str]:
    stripped = sql.strip()

    # Must be SELECT only — no multiple statements
    if ";" in stripped:
        # Allow exactly one trailing semicolon
        single = stripped.rstrip(";")
        if ";" in single:
            return False, "不支持多语句查询"
        stripped = single

    upper = stripped.upper()

    # Must start with SELECT
    if not upper.startswith("SELECT"):
        return False, "只允许执行 SELECT 查询"

    # Disallow dangerous keywords
    dangerous = [
        "PRAGMA",
        "ATTACH",
        "DETACH",
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "REPLACE",
        "VACUUM",
        "REINDEX",
        "GRANT",
        "REVOKE",
    ]
    for kw in dangerous:
        if re.search(r"\b" + kw + r"\b", upper):
            return False, f"不允许使用 {kw}"

    # Check for disallowed tables
    for table in _DENIED_TABLES:
        if re.search(r"\b" + re.escape(table) + r"\b", upper, re.IGNORECASE):
            return False, "查询包含未授权的数据表"

    # For extra safety, reject any table reference not in the allowlist
    # Find all potential table references (after FROM / JOIN)
    table_refs = set()
    for m in re.finditer(
        r"\b(?:FROM|JOIN)\s+(\w+)",
        upper,
        re.IGNORECASE,
    ):
        table_refs.add(m.group(1).lower())
    for table in table_refs:
        if table in _DENIED_TABLES:
            return False, "查询包含未授权的数据表"
        if table not in _ALLOWED_TABLES:
            # Unknown table — deny by default
            return False, "查询包含未授权的数据表"

    return True, ""
