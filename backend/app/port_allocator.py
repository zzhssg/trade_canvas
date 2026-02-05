"""Port allocation for worktree services."""
from __future__ import annotations

import socket

BASE_BACKEND_PORT = 8000
BASE_FRONTEND_PORT = 5173
MAX_WORKTREES = 99


class NoAvailablePortsError(Exception):
    """Raised when no available port pair can be found."""

    pass


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        return s.connect_ex((host, port)) != 0


def allocate_ports(
    used_backend: set[int] | None = None,
    used_frontend: set[int] | None = None,
) -> tuple[int, int]:
    """
    Find next available port pair for backend and frontend.

    Args:
        used_backend: Set of already allocated backend ports
        used_frontend: Set of already allocated frontend ports

    Returns:
        Tuple of (backend_port, frontend_port)

    Raises:
        NoAvailablePortsError: If no available port pair can be found
    """
    used_backend = used_backend or set()
    used_frontend = used_frontend or set()

    for i in range(1, MAX_WORKTREES + 1):
        backend = BASE_BACKEND_PORT + i
        frontend = BASE_FRONTEND_PORT + i
        if backend in used_backend or frontend in used_frontend:
            continue
        if is_port_available(backend) and is_port_available(frontend):
            return backend, frontend

    raise NoAvailablePortsError("No available port pair found")


def get_main_ports() -> tuple[int, int]:
    """Get the default ports for main worktree."""
    return BASE_BACKEND_PORT, BASE_FRONTEND_PORT
