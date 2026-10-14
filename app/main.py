from pathlib import Path
import json
import tempfile

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from .config import Settings
from .conversation import ConversationStore
from .errors import RagError
from .ollama import OllamaClient
from .prompts import DEFAULT_PROMPT, PROMPT_PRESETS, preset_payload
from .store import DocumentStore

settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
ollama = OllamaClient(settings.ollama_base_url, settings.chat_model, settings.embed_model)
store = DocumentStore(settings.data_dir, ollama, settings.chunk_size, settings.chunk_overlap, settings.top_k)
conversation = ConversationStore(settings.data_dir)
current_prompt = DEFAULT_PROMPT
app = FastAPI(title="Local Document RAG")


def _load_prompt(data_dir: Path) -> str:
    path = data_dir / "prompt.json"
    if not path.exists():
        return DEFAULT_PROMPT
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("prompt", "")
    except (OSError, json.JSONDecodeError):
        return DEFAULT_PROMPT
    return value.strip() or DEFAULT_PROMPT


def _save_prompt(data_dir: Path, prompt: str) -> None:
    (data_dir / "prompt.json").write_text(
        json.dumps({"prompt": prompt}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


current_prompt = _load_prompt(settings.data_dir)


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
        "data_dir": str(store.data_dir.resolve()),
        "uploads_dir": str(store.uploads_dir.resolve()),
        "chroma_dir": str((store.data_dir / "chroma").resolve()),
        "prompt": current_prompt,
        **conversation.status(),
        "chat_model": settings.chat_model,
        "embed_model": settings.embed_model,
        "ollama_url": settings.ollama_base_url,
    }


@app.post("/api/settings/data-dir")
async def set_data_dir(payload: dict[str, str]) -> dict[str, str | int]:
    requested = payload.get("data_dir", "").strip()
    if not requested:
        return JSONResponse({"error": "请输入 RAG 数据库保存目录。"}, status_code=400)
    data_dir = Path(requested).expanduser()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        data_dir = data_dir.resolve()
        global conversation, current_prompt, store
        store = DocumentStore(
            data_dir,
            ollama,
            settings.chunk_size,
            settings.chunk_overlap,
            settings.top_k,
        )
        current_prompt = _load_prompt(data_dir)
        conversation = ConversationStore(data_dir)
    except (OSError, ValueError) as exc:
        return JSONResponse({"error": f"无法使用该保存目录：{exc}"}, status_code=400)
    return {
        "data_dir": str(store.data_dir),
        "uploads_dir": str(store.uploads_dir),
        "chroma_dir": str((store.data_dir / "chroma").resolve()),
        "conversation_file": str(conversation.path.resolve()),
        **store.status(),
    }


@app.get("/api/prompts")
async def prompts() -> dict[str, object]:
    return {"presets": preset_payload(), "current_prompt": current_prompt}


@app.get("/api/conversation")
async def get_conversation() -> dict[str, object]:
    return {
        **conversation.status(),
        "messages": [{"role": item.role, "content": item.content} for item in conversation.messages],
    }


@app.post("/api/conversation/clear")
async def clear_conversation() -> dict[str, str | int]:
    conversation.clear()
    return conversation.status()


@app.post("/api/conversation/compress")
async def compress_conversation() -> dict[str, str | int]:
    if not conversation.messages:
        return JSONResponse({"error": "暂无可压缩的对话记录。"}, status_code=400)
    summary = await _compress_conversation()
    conversation.replace_with_summary(summary)
    return conversation.status()


async def _compress_conversation() -> str:
    return ollama.summarize(conversation.context())


@app.post("/api/settings/prompt")
async def set_prompt(payload: dict[str, str]) -> dict[str, str]:
    prompt = payload.get("prompt", "").strip()
    if not prompt:
        return JSONResponse({"error": "请输入模型提示词。"}, status_code=400)
    if len(prompt) > 10000:
        return JSONResponse({"error": "模型提示词不能超过 10000 个字符。"}, status_code=400)
    try:
        global current_prompt
        current_prompt = prompt
        _save_prompt(store.data_dir, current_prompt)
    except OSError as exc:
        return JSONResponse({"error": f"无法保存模型提示词：{exc}"}, status_code=400)
    return {"prompt": current_prompt, "data_dir": str(store.data_dir.resolve())}


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
    if not store.collection.count():
        return {"answer": "目前没有已索引的文档，请先导入文档。", "sources": []}
    results = store.search(question)
    if not results:
        return {"answer": "目前没有已索引的文档。", "sources": []}
    context = "\n\n".join(f"[来源：{item.filename}]\n{item.text}" for item in results)
    conversation_context = conversation.context()
    answer = ollama.answer(question, context, current_prompt, conversation_context)
    conversation.add("user", question)
    conversation.add("assistant", answer)
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
<section><h2>RAG 数据库位置</h2><p class="muted">请输入运行本应用的电脑上的文件夹路径。修改后，新导入的文档和索引会保存到该位置。</p>
<input id="data-dir" type="text" style="width:75%" placeholder="例如：A:\\rag-data">
<button onclick="saveDataDir()">保存位置</button><p id="data-dir-result"></p></section>
<section><h2>导入文档</h2><input id="file" type="file" accept=".pdf,.docx,.md,.markdown,.txt">
<button onclick="upload()">导入并建立索引</button> <button onclick="rebuild()">重建索引</button><p id="upload-result"></p></section>
<section><h2>索引状态</h2><p id="status">加载中...</p><ul id="docs"></ul></section>
<section><h2>模型提示词</h2><p class="muted">提示词会作为系统指令影响模型的回答方式，并保存到当前 RAG 数据目录。</p>
<select id="prompt-preset" onchange="usePreset()"><option value="">选择职业提示词...</option></select>
<textarea id="system-prompt" style="min-height:130px" placeholder="请输入自定义模型提示词"></textarea>
<button onclick="savePrompt()">保存提示词</button><p id="prompt-result"></p></section>
<section><h2>对话记录</h2><p id="conversation-status">加载中...</p>
<button onclick="compressConversation()">压缩生成摘要</button>
<button onclick="clearConversation()">清理对话记录</button><p id="conversation-result"></p>
<div id="conversation-list"></div></section>
<section><h2>问答</h2><textarea id="question" placeholder="例如：这几份文档的主要结论是什么？"></textarea>
<button onclick="ask()">提问</button><div id="answer"></div></section>
<script>
async function call(url, options){const r=await fetch(url,options);const data=await r.json();if(!r.ok)throw Error(data.error||'请求失败');return data}
async function refresh(){try{const s=await call('/api/status');document.querySelector('#status').innerHTML=`${s.documents} 个文档，${s.chunks} 个文本块；模型：${s.chat_model} / ${s.embed_model}<br><b>保存位置：</b>${s.data_dir}<br><span class="muted">上传文件：${s.uploads_dir}<br>Chroma 索引：${s.chroma_dir}<br>对话记录：${s.conversation_file}</span>`;document.querySelector('#data-dir').value=s.data_dir;document.querySelector('#system-prompt').value=s.prompt;document.querySelector('#docs').innerHTML=s.documents?'':'暂无文档';loadPrompts();loadConversation()}catch(e){document.querySelector('#status').innerHTML='<span class="error">'+e.message+'</span>'}}
async function loadPrompts(){try{const d=await call('/api/prompts');const select=document.querySelector('#prompt-preset');select.innerHTML='<option value="">选择职业提示词...</option>'+d.presets.map(x=>`<option value="${x.key}">${x.name}</option>`).join('');document.querySelector('#system-prompt').value=d.current_prompt}catch(e){}}
async function usePreset(){const key=document.querySelector('#prompt-preset').value;if(!key)return;const d=await call('/api/prompts');const preset=d.presets.find(x=>x.key===key);if(preset)document.querySelector('#system-prompt').value=preset.prompt}
async function savePrompt(){const p=document.querySelector('#prompt-result');const prompt=document.querySelector('#system-prompt').value.trim();if(!prompt){p.innerHTML='<span class="error">请输入模型提示词。</span>';return}p.textContent='保存中...';try{const d=await call('/api/settings/prompt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});p.textContent=`提示词已保存到：${d.data_dir}`}catch(e){p.innerHTML='<span class="error">'+e.message+'</span>'}}
async function loadConversation(){try{const d=await call('/api/conversation');document.querySelector('#conversation-status').textContent=`${d.message_count} 条消息${d.has_summary?'，已有摘要':''}；保存位置：${d.conversation_file}`;document.querySelector('#conversation-list').innerHTML=(d.summary?'<p><b>摘要：</b>'+d.summary+'</p>':'')+(d.messages||[]).map(x=>`<p><b>${x.role==='user'?'用户':'助手'}：</b>${x.content}</p>`).join('')}catch(e){document.querySelector('#conversation-status').innerHTML='<span class="error">'+e.message+'</span>'}}
async function compressConversation(){const p=document.querySelector('#conversation-result');p.textContent='摘要生成中...';try{await call('/api/conversation/compress',{method:'POST'});p.textContent='对话已压缩为摘要';loadConversation()}catch(e){p.innerHTML='<span class="error">'+e.message+'</span>'}}
async function clearConversation(){if(!confirm('确定清理当前对话记录吗？'))return;const p=document.querySelector('#conversation-result');try{await call('/api/conversation/clear',{method:'POST'});p.textContent='对话记录已清理';loadConversation()}catch(e){p.innerHTML='<span class="error">'+e.message+'</span>'}}
async function saveDataDir(){const p=document.querySelector('#data-dir-result');const dataDir=document.querySelector('#data-dir').value.trim();if(!dataDir){p.innerHTML='<span class="error">请输入保存目录。</span>';return}p.textContent='切换中...';try{const d=await call('/api/settings/data-dir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data_dir:dataDir})});p.textContent=`已切换保存位置：${d.data_dir}`;refresh()}catch(e){p.innerHTML='<span class="error">'+e.message+'</span>'}}
async function upload(){const f=document.querySelector('#file').files[0];if(!f)return;const p=document.querySelector('#upload-result');p.textContent='处理中...';try{const d=await call('/api/documents',{method:'POST',body:(()=>{const x=new FormData();x.append('file',f);return x})()});p.textContent=`已导入 ${d.filename}（${d.chunks} 个文本块）`;refresh()}catch(e){p.innerHTML='<span class="error">'+e.message+'</span>'}}
async function rebuild(){try{const d=await call('/api/rebuild',{method:'POST'});document.querySelector('#upload-result').textContent=`已重建 ${d.documents} 个文档`;refresh()}catch(e){document.querySelector('#upload-result').innerHTML='<span class="error">'+e.message+'</span>'}}
async function ask(){const a=document.querySelector('#answer');const question=document.querySelector('#question').value.trim();if(!question){a.innerHTML='<p class="error">请输入问题后再提问。</p>';return}a.textContent='生成回答中...';try{const d=await call('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});a.innerHTML='<p>'+d.answer.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('\\n','<br>')+'</p><p class="source"><b>来源：</b>'+d.sources.map(x=>x.filename).join('、')+'</p>'}catch(e){a.innerHTML='<p class="error">'+e.message+'</p>'}}
refresh()
</script></body></html>"""
