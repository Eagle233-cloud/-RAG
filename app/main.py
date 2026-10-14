from pathlib import Path
import tempfile

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from .config import Settings
from .errors import RagError
from .ollama import OllamaClient
from .store import DocumentStore

settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
ollama = OllamaClient(settings.ollama_base_url, settings.chat_model, settings.embed_model)
store = DocumentStore(settings.data_dir, ollama, settings.chunk_size, settings.chunk_overlap, settings.top_k)
app = FastAPI(title="Local Document RAG")


@app.exception_handler(RagError)
async def rag_error_handler(_: Request, exc: RagError) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML


@app.get("/api/status")
async def status() -> dict:
    return {
        **store.status(),
        "chat_model": settings.chat_model,
        "embed_model": settings.embed_model,
        "ollama_url": settings.ollama_base_url,
    }


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if not file.filename or suffix not in {".pdf", ".docx", ".md", ".markdown", ".txt"}:
        return JSONResponse({"error": "仅支持 PDF、DOCX、Markdown 和 TXT 文件。"}, status_code=400)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
        temporary.write(await file.read())
        source = Path(temporary.name)
    try:
        return store.index_file(source)
    finally:
        source.unlink(missing_ok=True)


@app.post("/api/rebuild")
async def rebuild() -> dict[str, int]:
    return {"documents": store.rebuild()}


@app.post("/api/ask")
async def ask(payload: dict[str, str]) -> dict:
    question = payload.get("question", "").strip()
    if not question:
        return JSONResponse({"error": "请输入问题。"}, status_code=400)
    results = store.search(question)
    if not results:
        return {"answer": "目前没有已索引的文档。", "sources": []}
    context = "\n\n".join(f"[来源：{item.filename}]\n{item.text}" for item in results)
    answer = ollama.answer(question, context)
    return {
        "answer": answer,
        "sources": [{"filename": item.filename, "distance": round(item.distance, 4)} for item in results],
    }


HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>本地文档 RAG</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1f2937}
section{border:1px solid #d1d5db;border-radius:10px;padding:1rem;margin:1rem 0} button{cursor:pointer;padding:.5rem .8rem}
textarea{width:100%;min-height:90px;margin:.5rem 0} .muted{color:#6b7280}.error{color:#b91c1c}.source{font-size:.9rem}
ul{padding-left:1.2rem}
</style></head><body><h1>本地文档 RAG</h1>
<p class="muted">Ollama + Chroma · 支持 PDF、Word、Markdown、TXT</p>
<section><h2>导入文档</h2><input id="file" type="file" accept=".pdf,.docx,.md,.markdown,.txt">
<button onclick="upload()">导入并建立索引</button> <button onclick="rebuild()">重建索引</button><p id="upload-result"></p></section>
<section><h2>索引状态</h2><p id="status">加载中...</p><ul id="docs"></ul></section>
<section><h2>问答</h2><textarea id="question" placeholder="例如：这几份文档的主要结论是什么？"></textarea>
<button onclick="ask()">提问</button><div id="answer"></div></section>
<script>
async function call(url, options){const r=await fetch(url,options);const data=await r.json();if(!r.ok)throw Error(data.error||'请求失败');return data}
async function refresh(){try{const s=await call('/api/status');document.querySelector('#status').textContent=`${s.documents} 个文档，${s.chunks} 个文本块；模型：${s.chat_model} / ${s.embed_model}`;document.querySelector('#docs').innerHTML=(await call('/api/status')).documents?'':'暂无文档';}catch(e){document.querySelector('#status').innerHTML='<span class="error">'+e.message+'</span>'}}
async function upload(){const f=document.querySelector('#file').files[0];if(!f)return;const p=document.querySelector('#upload-result');p.textContent='处理中...';try{const d=await call('/api/documents',{method:'POST',body:(()=>{const x=new FormData();x.append('file',f);return x})()});p.textContent=`已导入 ${d.filename}（${d.chunks} 个文本块）`;refresh()}catch(e){p.innerHTML='<span class="error">'+e.message+'</span>'}}
async function rebuild(){try{const d=await call('/api/rebuild',{method:'POST'});document.querySelector('#upload-result').textContent=`已重建 ${d.documents} 个文档`;refresh()}catch(e){document.querySelector('#upload-result').innerHTML='<span class="error">'+e.message+'</span>'}}
async function ask(){const a=document.querySelector('#answer');a.textContent='生成回答中...';try{const d=await call('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:document.querySelector('#question').value})});a.innerHTML='<p>'+d.answer.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('\\n','<br>')+'</p><p class="source"><b>来源：</b>'+d.sources.map(x=>x.filename).join('、')+'</p>'}catch(e){a.innerHTML='<p class="error">'+e.message+'</p>'}}
refresh()
</script></body></html>"""

