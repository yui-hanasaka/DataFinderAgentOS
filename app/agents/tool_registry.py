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
            "description": (
                "在安全沙箱中执行Python代码。适合网络爬虫、HTML解析、数据提取、"
                "文件下载、格式转换、数学运算等。可用的第三方库：httpx（HTTP请求，"
                "支持自定义UA/Cookie/Header绕过反爬）、BeautifulSoup（HTML解析）、"
                "urllib。执行目录下可读写文件，文件会保留供后续代码继续处理。"
                "当 web_search 失败时，优先用此工具编写 Python 爬虫直接搜索。"
            ),
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
            "name": "web_fetch",
            "description": (
                "下载指定URL的网页HTML内容并保存到工作区。返回文件路径和内容预览。"
                "适合先下载页面，再用 code_execute 工具编写 BeautifulSoup 脚本解析提取数据。"
                "当需要分析特定网页结构时优先使用此工具下载，避免在 code_execute 中直接请求。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要下载的网页URL"},
                    "save_html": {
                        "type": "boolean",
                        "description": "是否保存HTML到工作区文件，默认true",
                        "default": True,
                    },
                },
                "required": ["url"],
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
    {
        "type": "function",
        "function": {
            "name": "weather_query",
            "description": (
                "查询指定城市的天气，支持实时天气、多天预报、逐小时预报、分钟级降水、"
                "18项生活指数、空气质量及污染物分项、气象预警等。"
                "当用户询问天气、温度、下雨、穿衣、出行等问题时使用此工具。"
                "默认返回所有模块（extended+forecast+hourly+minutely+indices），"
                "可根据用户具体需求选择性关闭。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，中文（如'南充'）或英文（如'Tokyo'）。也可传 adcode 行政区划代码（如'110000'）替代 city。",
                    },
                    "adcode": {
                        "type": "string",
                        "description": "行政区划代码（如'110000'），优先级高于 city。不传则按城市名查询。",
                    },
                    "forecast": {
                        "type": "boolean",
                        "description": "是否返回7天预报（含每天最高/最低温、白天夜间天气、日出日落等），默认true",
                        "default": True,
                    },
                    "hourly": {
                        "type": "boolean",
                        "description": "是否返回24小时逐小时预报（含温度、降水概率、体感温度等），默认true",
                        "default": True,
                    },
                    "minutely": {
                        "type": "boolean",
                        "description": "是否返回分钟级降水预报（仅国内城市，精确到2分钟），默认true",
                        "default": True,
                    },
                    "indices": {
                        "type": "boolean",
                        "description": (
                            "是否返回18项生活指数（穿衣/紫外线/洗车/运动/感冒/出行/"
                            "钓鱼/过敏/防晒/心情/雨伞/花粉等），默认true"
                        ),
                        "default": True,
                    },
                    "lang": {
                        "type": "string",
                        "description": "返回语言：zh=中文（默认），en=英文",
                        "default": "zh",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "music_search",
            "description": (
                "搜索歌曲。返回歌曲列表（含歌曲ID、歌名、歌手、专辑）。"
                "搜索到结果后，列出歌曲让用户选择播放哪一首。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，歌名或歌手名",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "music_play",
            "description": (
                "根据歌曲ID生成网易云音乐官方播放器iframe。"
                "用户确认要播放某首歌后调用此工具展示播放器。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "song_id": {
                        "type": "integer",
                        "description": "网易云音乐歌曲ID（从 music_search 结果中获取）",
                    },
                    "title": {
                        "type": "string",
                        "description": "歌曲名称（用于展示）",
                    },
                    "artist": {
                        "type": "string",
                        "description": "歌手名称（用于展示）",
                    },
                },
                "required": ["song_id"],
            },
        },
    },
]
