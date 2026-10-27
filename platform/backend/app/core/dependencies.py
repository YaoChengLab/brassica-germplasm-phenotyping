"""
Shared dependencies for FastAPI endpoints
- Database session management
- Operator identity

The platform has no login. Every request runs as one fixed operator, whose
name is recorded where the platform keeps provenance (batch milestones,
export manifests, logs). Anyone who can reach the API can therefore write to
the database, so deploy it on localhost or a trusted network only.
"""

import os
from types import SimpleNamespace

from sqlalchemy.orm import Session

from ..config.database import SessionLocal


# Name recorded as the operator; set BPP_OPERATOR to override.
OPERATOR = SimpleNamespace(
    username=os.getenv("BPP_OPERATOR", "admin"),
    is_admin=True,
)


def get_db() -> Session:
    """Dependency for database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user():
    """Dependency returning the fixed operator."""
    return OPERATOR


def get_admin_user():
    """Dependency returning the fixed operator, who holds admin rights."""
    return OPERATOR
