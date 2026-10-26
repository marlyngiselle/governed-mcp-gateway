from collections.abc import Callable

import pytest

from governed_mcp.gateway import GovernedServer
from governed_mcp.gateway.core import current_identity
from tests.conftest import Harness


def server(make: Callable[..., Harness]) -> GovernedServer:
    return make("runbooks").server


def test_plain_tool_decorator_is_refused(make: Callable[..., Harness]) -> None:
    with pytest.raises(TypeError, match="governed_tool"):
        server(make).tool()


def test_write_tool_must_declare_confirm(make: Callable[..., Harness]) -> None:
    s = server(make)
    with pytest.raises(TypeError, match="confirm"):

        @s.governed_tool(access="write")
        async def delete_everything() -> str:
            return "gone"

    with pytest.raises(TypeError, match="confirm"):

        @s.governed_tool(access="write")
        async def sneaky(confirm: bool = True) -> str:
            return "defaults to yes"


def test_sync_tools_are_refused(make: Callable[..., Harness]) -> None:
    s = server(make)

    def sync_tool() -> str:
        return "x"

    with pytest.raises(TypeError, match="async"):
        s.governed_tool(access="read")(sync_tool)  # type: ignore[arg-type]


def test_current_identity_outside_a_call_is_an_error() -> None:
    with pytest.raises(RuntimeError):
        current_identity()
