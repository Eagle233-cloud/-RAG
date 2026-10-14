from typing import Any

import httpx

from .errors import ModelMissingError, OllamaUnavailableError


class OllamaClient:
    def __init__(self, base_url: str, chat_model: str, embed_model: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = httpx.request(method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(
                f"无法连接 Ollama（{self.base_url}）。请确认 Ollama 已启动。"
            ) from exc
        if response.status_code == 404:
            raise OllamaUnavailableError("Ollama 服务未找到，请确认地址和服务版本正确。")
        if response.status_code >= 400:
            detail = response.text[:300]
            raise OllamaUnavailableError(f"Ollama 请求失败（HTTP {response.status_code}）：{detail}")
        return response.json()

    def available_models(self) -> set[str]:
        data = self._request("GET", "/api/tags")
        return {item.get("name", "").split(":")[0] for item in data.get("models", [])}

    def check_models(self) -> None:
        models = self.available_models()
        missing = [name for name in (self.embed_model, self.chat_model) if name.split(":")[0] not in models]
        if missing:
            raise ModelMissingError(f"缺少 Ollama 模型：{', '.join(missing)}。请运行 ollama pull <模型名>。")

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.check_models()
        result = self._request("POST", "/api/embed", json={"model": self.embed_model, "input": texts})
        embeddings = result.get("embeddings")
        if not embeddings:
            raise OllamaUnavailableError("Ollama 未返回有效的文档向量。")
        return embeddings

    def answer(self, question: str, context: str) -> str:
        self.check_models()
        prompt = (
            "你是一个本地文档问答助手。仅根据下面提供的资料回答问题；"
            "资料不足时明确说“文档中没有足够信息”，不要编造。用中文简洁回答。\n\n"
            f"资料：\n{context}\n\n问题：{question}"
        )
        result = self._request(
            "POST",
            "/api/chat",
            json={
                "model": self.chat_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        )
        content = result.get("message", {}).get("content", "").strip()
        if not content:
            raise OllamaUnavailableError("Ollama 未返回有效回答。")
        return content

