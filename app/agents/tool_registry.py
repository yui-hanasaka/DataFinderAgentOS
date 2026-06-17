from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网获取实时信息和新闻",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或问题"},
                    "max_results": {
                        "type": "integer",
                        "description": "最多返回结果数，默认5",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_execute",
            "description": "在安全沙箱中执行Python代码，适合数据计算、格式转换、数学运算等",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要执行的Python代码"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "watchtower_search",
            "description": "搜索数据瞭望已采集的新闻和资讯条目",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "string", "description": "搜索关键词"},
                    "limit": {
                        "type": "integer",
                        "description": "返回条数，默认20",
                        "default": 20,
                    },
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "warehouse_query",
            "description": "对数据仓库进行查询，获取采集数据的统计和分析结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用自然语言描述的查询问题",
                    },
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deep_collect",
            "description": "对指定URL进行AI深度内容采集与分析，提取摘要、关键词、情感",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要深度采集的网页URL"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "env_info",
            "description": "检查当前Python环境信息、版本和已安装的关键依赖包",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
