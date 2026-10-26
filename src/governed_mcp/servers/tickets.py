"""tickets: search incident tickets and, with confirmation, open new ones."""

from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from governed_mcp.adapters.tickets import Severity, Status, TicketStore
from governed_mcp.config import Settings
from governed_mcp.gateway import Gateway, GovernedServer
from governed_mcp.gateway.core import current_identity

Service = Annotated[
    str, Field(pattern=r"^[a-z][a-z0-9-]{1,31}$", description="Owning service, e.g. platform.")
]


def build(
    gateway: Gateway, settings: Settings, *, store: TicketStore | None = None, **server_options: Any
) -> GovernedServer:
    tickets = store or TicketStore()
    server = GovernedServer(
        "tickets",
        gateway=gateway,
        **server_options,
        instructions=(
            "Incident tickets. create_ticket changes state: describe the ticket to the user and "
            "call it with confirm=true only after they agree."
        ),
    )

    @server.governed_tool(access="read", title="Search tickets")
    async def search_tickets(
        query: Annotated[str | None, Field(max_length=100)] = None,
        status: Status | None = None,
        severity: Severity | None = None,
        service: Service | None = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> dict[str, Any]:
        """Search tickets by text, status, severity and service."""
        found = tickets.search(query, status, severity, service)
        return {"total": len(found), "tickets": [t.model_dump() for t in found[:limit]]}

    @server.governed_tool(access="read", title="Get ticket")
    async def get_ticket(
        ticket_id: Annotated[str, Field(pattern=r"^TCK-\d{4,6}$", description="Ticket id, e.g. TCK-1002.")],
    ) -> dict[str, Any]:
        """Get one ticket by id."""
        ticket = tickets.get(ticket_id)
        if ticket is None:
            raise ToolError(f"ticket {ticket_id} not found")
        return ticket.model_dump()

    @server.governed_tool(access="write", title="Create ticket")
    async def create_ticket(
        title: Annotated[str, Field(min_length=5, max_length=120)],
        description: Annotated[str, Field(min_length=10, max_length=4000)],
        service: Service,
        severity: Annotated[
            Literal["sev2", "sev3", "sev4"],
            Field(description="sev1 pages people out of hours, so only humans open it."),
        ] = "sev3",
        confirm: Annotated[
            bool, Field(description="Must be true. Set it only after the user approved this exact ticket.")
        ] = False,
    ) -> dict[str, Any]:
        """Open a new incident ticket. Write action: needs confirm=true after user approval."""
        ticket = tickets.create(
            title=title,
            description=description,
            severity=severity,
            service=service,
            reporter=current_identity().principal,
        )
        return {"created": True, "ticket": ticket.model_dump()}

    return server
