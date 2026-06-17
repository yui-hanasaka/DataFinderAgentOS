import gc
import os
import tempfile
from collections.abc import Generator

import pytest

import app.models.db as db_module


@pytest.fixture()
def db_with_user() -> Generator[int, None, None]:
    path = tempfile.mktemp(suffix=".db")
    db_module.DB_PATH = path
    db_module.init_db()
    with db_module.get_connection() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, salt) VALUES('u1','h','s')"
        )
        uid: int = conn.execute("SELECT id FROM users WHERE username='u1'").fetchone()[
            "id"
        ]
    yield uid
    gc.collect()
    try:
        if os.path.exists(path):
            os.remove(path)
    except PermissionError:
        pass


def test_create_and_get_session(db_with_user: int) -> None:
    from app.models.chat import ChatRepository

    sid, err = ChatRepository.create_session(db_with_user, 0, "测试对话")
    assert err is None and sid is not None
    sess = ChatRepository.get_session(sid)
    assert sess is not None
    assert sess["title"] == "测试对话"


def test_add_and_list_messages(db_with_user: int) -> None:
    from app.models.chat import ChatRepository

    sid, _ = ChatRepository.create_session(db_with_user, 0, "t")
    assert sid is not None
    ChatRepository.add_message(sid, "user", "你好")
    ChatRepository.add_message(sid, "assistant", "你好！")
    msgs = ChatRepository.list_messages(sid)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"


def test_delete_session_cascades(db_with_user: int) -> None:
    from app.models.chat import ChatRepository

    sid, _ = ChatRepository.create_session(db_with_user, 0, "del")
    assert sid is not None
    ChatRepository.add_message(sid, "user", "test")
    ChatRepository.delete_session(sid)
    assert ChatRepository.get_session(sid) is None
    assert ChatRepository.list_messages(sid) == []


def test_count_sessions(db_with_user: int) -> None:
    from app.models.chat import ChatRepository

    ChatRepository.create_session(db_with_user, 0, "s1")
    ChatRepository.create_session(db_with_user, 0, "s2")
    assert ChatRepository.count_all_sessions() >= 2
