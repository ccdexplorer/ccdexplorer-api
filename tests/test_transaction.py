# test_app.py
from contextlib import asynccontextmanager
import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

# from starlette.testclient import ASGITransport


@pytest_asyncio.fixture
async def app():
    @asynccontextmanager
    async def lifespan(app):
        print("Starting up")
        yield
        print("Shutting down")

    async def home(request):
        return PlainTextResponse("Hello, world!")

    app = Starlette(
        routes=[Route("/", home)],
        lifespan=lifespan,
    )

    async with LifespanManager(app) as manager:
        print("We're in!")
        yield manager.app


@pytest.mark.asyncio(loop_scope="session")
@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:7000"
    ) as client:
        print("Client is ready")
        yield client


@pytest.mark.asyncio
async def test_home(client):
    print("Testing")
    response = await client.get("/")
    assert response.status_code == 200
    assert response.text == "Hello, world!"
    print("OK")
