import json
import typing as tp
from dataclasses import dataclass


@dataclass
class ToolCallRecord:
    name: str
    args: dict
    result: tp.Any = None


class ToolTracer:
    def __init__(self):
        self.calls: list[ToolCallRecord] = []

    def record(self, name: str, args: dict, result: tp.Any = None) -> None:
        self.calls.append(ToolCallRecord(name=name, args=args, result=result))

    def called(self, name: str) -> bool:
        return any(c.name == name for c in self.calls)

    def get_calls(self, name: str) -> list:
        return [c for c in self.calls if c.name == name]

    def print_trace(self) -> None:
        print("=== Tool Call Trace ===")
        for i, c in enumerate(self.calls, 1):
            print(f"  {i}. {c.name}({json.dumps(c.args, ensure_ascii=False)[:80]})")
            if c.result is not None:
                print(f"     -> {json.dumps(c.result, ensure_ascii=False)[:100]}")
        print("=====================")
