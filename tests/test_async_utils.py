import pytest

from typing import AsyncIterator

import asyncio

from pole.async_utils import eager_async_iter


class TestEagerAsyncIter:
    async def test_simple_iterator(self) -> None:
        done = asyncio.Event()

        async def example() -> AsyncIterator[int]:
            yield 1
            yield 2
            yield 3
            done.set()

        async_iter = eager_async_iter(example())

        # The iterator should run in the background
        await asyncio.wait_for(done.wait(), 1)

        # And we should get the values out
        assert await async_iter.__anext__() == 1
        assert await async_iter.__anext__() == 2
        assert await async_iter.__anext__() == 3
        with pytest.raises(StopAsyncIteration):
            await async_iter.__anext__()

    async def test_iterator_crashes(self) -> None:
        async def example() -> AsyncIterator[int]:
            yield 1
            raise NotImplementedError()

        async_iter = eager_async_iter(example())

        assert await async_iter.__anext__() == 1

        # Iterator's exception should come out
        with pytest.raises(NotImplementedError):
            await async_iter.__anext__()

    async def test_buffer_limit_and_cancel(self) -> None:
        cancelled = asyncio.Event()
        generated = []

        async def example() -> AsyncIterator[int]:
            try:
                for i in range(1, 10):
                    generated.append(i)
                    yield i
            except GeneratorExit:
                cancelled.set()
                raise

        async_iter = eager_async_iter(example(), 2)

        # Make sure iterator has started
        assert await async_iter.__anext__() == 1
        assert await async_iter.__anext__() == 2
        assert await async_iter.__anext__() == 3

        # Stop the iterator
        await async_iter.aclose()

        # Make sure the iterator was stopped
        await asyncio.wait_for(cancelled.wait(), 1)

        # Should have buffered up two extras beyond the '3' above
        assert generated == [1, 2, 3, 4, 5]
