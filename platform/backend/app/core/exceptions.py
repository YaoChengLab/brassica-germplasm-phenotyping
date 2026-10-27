from fastapi import HTTPException as FastAPIHTTPException

class HTTPException(FastAPIHTTPException):
    """Custom HTTP Exception"""
    pass

class DatabaseError(Exception):
    """Database operation error"""
    pass

class ValidationError(Exception):
    """Data validation error"""
    pass