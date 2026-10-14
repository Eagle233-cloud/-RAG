import httpx
import pytest

from app.errors import ModelMissingError, OllamaUnavailableError
from app.ollama import OllamaClient


def test_missing_models(monkeypatch):
    def fake_request(*args, **kwargs):
        return httpx.Response(200, json={"models": [{"name": "llama3.2:latest"}]})

    monkeypatch.setattr(httpx, "request", fake_request)
    client = OllamaClient("http://ollama", "llama3.2", "nomic-embed-text")
    with pytest.raises(ModelMissingError):
        client.check_models()


def test_unavailable_ollama(monkeypatch):
    def fake_request(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "request", fake_request)
    with pytest.raises(OllamaUnavailableError):
        OllamaClient("http://ollama", "chat", "embed").available_models()

