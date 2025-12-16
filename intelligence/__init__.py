"""
Intelligence layer: Pure state transition logic.
No side effects, no DB calls, no filesystem I/O.
"""

# Export main handler function for easy access
from intelligence.handler import handle_inbound

__all__ = ["handle_inbound"]
