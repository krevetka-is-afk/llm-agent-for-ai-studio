import asyncio

from ai_studio_agent_builder.presentation.telegram.request_gate import (
    PerUserRequestGate,
)


def test_same_user_requests_are_serialized() -> None:
    async def scenario() -> list[str]:
        gate = PerUserRequestGate()
        entered: list[str] = []
        first_entered = asyncio.Event()
        release_first = asyncio.Event()

        async def first() -> None:
            async with gate.hold("42"):
                entered.append("first")
                first_entered.set()
                await release_first.wait()

        async def second() -> None:
            await first_entered.wait()
            async with gate.hold("42"):
                entered.append("second")

        first_task = asyncio.create_task(first())
        second_task = asyncio.create_task(second())
        await first_entered.wait()
        await asyncio.sleep(0)
        assert entered == ["first"]
        release_first.set()
        await asyncio.gather(first_task, second_task)
        return entered

    assert asyncio.run(scenario()) == ["first", "second"]


def test_different_users_are_not_globally_blocked() -> None:
    async def scenario() -> set[str]:
        gate = PerUserRequestGate()
        entered: set[str] = set()
        both_entered = asyncio.Event()
        release = asyncio.Event()

        async def worker(user_id: str) -> None:
            async with gate.hold(user_id):
                entered.add(user_id)
                if len(entered) == 2:
                    both_entered.set()
                await release.wait()

        tasks = [
            asyncio.create_task(worker("42")),
            asyncio.create_task(worker("84")),
        ]
        await asyncio.wait_for(both_entered.wait(), timeout=1)
        release.set()
        await asyncio.gather(*tasks)
        return entered

    assert asyncio.run(scenario()) == {"42", "84"}


def test_global_request_concurrency_is_bounded() -> None:
    async def scenario() -> list[str]:
        gate = PerUserRequestGate(max_concurrent_requests=1)
        entered: list[str] = []
        first_entered = asyncio.Event()
        release_first = asyncio.Event()

        async def first() -> None:
            async with gate.hold("42"):
                entered.append("42")
                first_entered.set()
                await release_first.wait()

        async def second() -> None:
            await first_entered.wait()
            async with gate.hold("84"):
                entered.append("84")

        tasks = [asyncio.create_task(first()), asyncio.create_task(second())]
        await first_entered.wait()
        await asyncio.sleep(0)
        assert entered == ["42"]
        release_first.set()
        await asyncio.gather(*tasks)
        return entered

    assert asyncio.run(scenario()) == ["42", "84"]
