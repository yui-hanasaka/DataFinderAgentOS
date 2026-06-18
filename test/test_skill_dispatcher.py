import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_weather_skill() -> None:
    from app.models.skill_dispatcher import dispatch

    async def _test():
        result = await dispatch("@weather 重庆")
        assert result["type"] == "ai"
        assert result["skill_code"] == "weather"
        meta: dict[str, Any] = result["skill_meta"]
        assert "重庆" in str(meta.get("inject_prompt"))

    _run(_test())


def test_music_skill() -> None:
    from app.models.skill_dispatcher import dispatch

    async def _test():
        result = await dispatch("@music")
        assert result["type"] == "skill"
        assert result["skill_code"] == "music"

    _run(_test())


def test_campus_skill() -> None:
    from app.models.skill_dispatcher import dispatch

    async def _test():
        result = await dispatch("@西师妹 食堂几点开门")
        assert result["type"] == "ai"
        assert result["skill_code"] == "campus"
        meta: dict[str, Any] = result["skill_meta"]
        assert "西师妹" in str(meta.get("system_override"))

    _run(_test())


def test_search_skill() -> None:
    from app.models.skill_dispatcher import dispatch

    async def _test():
        with patch(
            "app.models.skill_dispatcher._web_search",
            new_callable=AsyncMock,
            return_value="mock",
        ) as mock:
            result = await dispatch(r"\search Python教程")
            mock.assert_called_once()
        assert result["type"] == "ai"
        assert result["skill_code"] == "websearch"

    _run(_test())


def test_plain_ai() -> None:
    from app.models.skill_dispatcher import dispatch

    async def _test():
        result = await dispatch("你好")
        assert result["type"] == "ai"
        assert result["skill_code"] is None
        assert result["processed_content"] == "你好"

    _run(_test())


def test_case_insensitive_weather() -> None:
    from app.models.skill_dispatcher import dispatch

    async def _test():
        result = await dispatch("@Weather 北京")
        assert result["skill_code"] == "weather"
        assert result["type"] == "ai"

    _run(_test())
