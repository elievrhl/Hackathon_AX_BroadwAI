import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver

from broadwai.models import canonical_url


class RetrievalError(Exception):
    pass


def check_public_ip(address: str) -> None:
    ip = ipaddress.ip_address(address.split("%")[0])
    mapped = getattr(ip, "ipv4_mapped", None)
    if not ip.is_global or (mapped and not mapped.is_global):
        raise RetrievalError("Destination réseau non publique interdite")


def validate_destination(url: str) -> str:
    url = canonical_url(url)
    host = urlsplit(url).hostname or ""
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise RetrievalError("Destination locale interdite")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        check_public_ip(host)
    return url


class PublicResolver(AbstractResolver):
    """Validate the actual IPs returned to the connector, avoiding a second DNS lookup."""

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        records = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            family=family,
            type=socket.SOCK_STREAM,
        )
        result = []
        for family, _, proto, _, address in records:
            check_public_ip(address[0])
            result.append(
                {
                    "hostname": host,
                    "host": address[0],
                    "port": port,
                    "family": family,
                    "proto": proto,
                    "flags": socket.AI_NUMERICHOST,
                }
            )
        if not result:
            raise RetrievalError("Aucune adresse publique")
        return result

    async def close(self):
        pass


@dataclass
class Download:
    url: str
    body: bytes
    content_type: str


class PublicFetcher:
    def __init__(self, timeout: float = 15, max_bytes: int = 2_000_000):
        self.timeout = timeout
        self.max_bytes = max_bytes

    async def get(self, url: str) -> Download:
        try:
            async with asyncio.timeout(self.timeout):
                connector = aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False)
                async with aiohttp.ClientSession(
                    connector=connector,
                    trust_env=False,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    headers={"User-Agent": "BroadwAI/0.1 (article reader)"},
                ) as session:
                    for _ in range(5):
                        url = validate_destination(url)
                        async with session.get(url, allow_redirects=False) as response:
                            if response.status in {301, 302, 303, 307, 308}:
                                location = response.headers.get("Location")
                                if not location:
                                    raise RetrievalError("Redirection sans destination")
                                url = urljoin(url, location)
                                continue
                            response.raise_for_status()
                            chunks = bytearray()
                            async for chunk in response.content.iter_chunked(16384):
                                chunks.extend(chunk)
                                if len(chunks) > self.max_bytes:
                                    raise RetrievalError("Document trop volumineux")
                            return Download(str(response.url), bytes(chunks), response.content_type)
                    raise RetrievalError("Trop de redirections")
        except (aiohttp.ClientError, TimeoutError, OSError, ValueError) as exc:
            # Avoid leaking credential-bearing URLs or provider response bodies.
            raise RetrievalError(f"Téléchargement impossible ({type(exc).__name__})") from exc
