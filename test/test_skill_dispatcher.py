from unittest.mock import patch


def test_weather_skill() -> None:
    from app.models.skill_dispatcher import dispatch

    result = dispatch("@weather 重庆")
    assert result["type"] == "skill"
    assert result["skill_code"] == "weather"
    assert result["skill_meta"]["city"] == "重庆"  # type: ignore[index]
    assert "未配置" in str(result["processed_content"])


def test_music_skill() -> None:
    from app.models.skill_dispatcher import dispatch

    result = dispatch("@music")
    assert result["type"] == "skill"
    assert result["skill_code"] == "music"


def test_campus_skill() -> None:
    from app.models.skill_dispatcher import dispatch

    result = dispatch("@西师妹 食堂几点开门")
    assert result["type"] == "ai"
    assert result["skill_code"] == "campus"
    assert "西师妹" in str(result["skill_meta"]["system_override"])  # type: ignore[index]


def test_search_skill() -> None:
    from app.models.skill_dispatcher import dispatch

    with patch("app.models.skill_dispatcher._web_search", return_value="mock") as mock:
        result = dispatch(r"\search Python教程")
        mock.assert_called_once()
    assert result["type"] == "ai"
    assert result["skill_code"] == "websearch"


def test_plain_ai() -> None:
    from app.models.skill_dispatcher import dispatch

    result = dispatch("你好")
    assert result["type"] == "ai"
    assert result["skill_code"] is None
    assert result["processed_content"] == "你好"


def test_case_insensitive_weather() -> None:
    from app.models.skill_dispatcher import dispatch

    assert dispatch("@Weather 北京")["skill_code"] == "weather"
