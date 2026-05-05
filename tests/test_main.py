from pathlib import Path

from src.context import ConversationState


def test_conversation_state_marks_done(tmp_path: str) -> None:
    state = ConversationState(Path(tmp_path))
    assert state.is_done() is False
    assert state.get_base_dir() == Path(tmp_path)

    state.set_done()
    assert state.is_done() is True
