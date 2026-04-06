"""Beats - Time tracking application.

This package provides a time tracking system with DDD architecture:
- domain/ - Core business logic and entities
- infrastructure/ - Database and external service integrations
- api/ - HTTP endpoints and request/response handling
"""

from beats.domain import Beat, Project

__all__ = ["Beat", "Project"]
