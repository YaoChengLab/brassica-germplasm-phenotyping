import ipaddress
import logging
import time
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def _parse_cidrs(cidr_string: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks = []
    for cidr in cidr_string.split(","):
        cidr = cidr.strip()
        if cidr:
            try:
                networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError:
                logger.warning(f"Invalid CIDR in ALLOWED_IP_CIDRS, skipping: {cidr!r}")
    return networks


def _is_ip_allowed(
    client_ip: str,
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    return any(addr in net for net in networks)


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """
    Server-side IP whitelist middleware.

    Blocks requests whose client IP does not fall within any of the
    configured CIDR ranges (ALLOWED_IP_CIDRS).  Paths listed in
    ip_whitelist_exempt_paths are always allowed (e.g. /health).
    """

    def __init__(self, app, allowed_ip_cidrs: str, exempt_paths: list[str]):
        super().__init__(app)
        self._networks = _parse_cidrs(allowed_ip_cidrs)
        self._exempt_paths = set(exempt_paths)
        logger.info(
            f"IPWhitelistMiddleware initialised with {len(self._networks)} network(s): "
            + ", ".join(str(n) for n in self._networks)
        )

    async def dispatch(self, request: Request, call_next):
        # Exempt configured paths
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        # Resolve client IP, respecting X-Forwarded-For when behind a reverse proxy
        forwarded_for = request.headers.get("X-Forwarded-For")
        client_ip = (
            forwarded_for.split(",")[0].strip()
            if forwarded_for
            else (request.client.host if request.client else "")
        )

        if not _is_ip_allowed(client_ip, self._networks):
            logger.warning(
                f"Blocked request from {client_ip!r} to {request.url.path}"
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Access Denied",
                    "message": "Your IP address is not permitted to access this service.",
                    "timestamp": time.time(),
                },
            )

        return await call_next(request)
