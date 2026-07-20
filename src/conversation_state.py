from enum import Enum, auto


class ConversationOptions(Enum):
    COORDINATOR = auto()
    RAG = auto()
    ONE_PROMPT = auto()


class ConversationState:
    def __init__(
        self, state: ConversationOptions = ConversationOptions.COORDINATOR
    ) -> None:
        self.state = state

    def copy(self) -> "ConversationState":
        return ConversationState(self.state)

    def update_state(self, new_state: ConversationOptions) -> None:
        self.state = new_state

    def reset_state(self) -> None:
        self.state = ConversationOptions.COORDINATOR
