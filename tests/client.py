"""Trusted operator client for existing domain/API tests.

Authentication and authorization are exercised without this override in test_auth.py.
These older tests deliberately probe multiple readers and administrator workflows.
"""

from fastapi import Request
from fastapi.testclient import TestClient as BaseTestClient

from broadwai.auth import authorize_request


async def trusted_operator(request: Request):
    request.state.account = {"id": "test-operator", "is_admin": True}


class TestClient(BaseTestClient):
    __test__ = False

    def __init__(self, app, *args, **kwargs):
        app.dependency_overrides[authorize_request] = trusted_operator
        super().__init__(app, *args, **kwargs)
