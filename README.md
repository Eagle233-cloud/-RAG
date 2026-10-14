# 本地文档 RAG

这是一个基于 **Ollama + Chroma + FastAPI** 的本地文档检索增强生成（RAG）应用。文档和问答数据保存在本机，适合对个人资料、项目文档和内部知识进行本地检索与问答。

## 功能

- 支持导入 PDF、Word（`.docx`）、Markdown（`.md`、`.markdown）和 TXT 文档
- 自动提取文本、分块并生成向量索引
- 使用 Chroma 持久化保存本地索引
- 使用 Ollama 生成文档向量和问答结果
- 提供简单的 Web 页面，用于上传文档、查看索引状态和提问
- 可在 Web 页面中切换 RAG 数据库保存目录
- 在索引状态中显示当前数据目录、上传文件目录和 Chroma 索引目录
- 回答中返回相关文档来源
- 检测并提示以下常见问题：
  - Ollama 服务未启动或无法连接
  - Ollama 聊天模型或嵌入模型缺失
  - 文件格式不支持
  - 文档内容为空
  - 文档重复导入
  - 索引重建失败

## 环境要求

- Windows、macOS 或 Linux
- Python 3.10 及以上
- 已安装并运行 [Ollama](https://ollama.com/)
- 已准备一个聊天模型和一个嵌入模型

## 安装与启动

请先进入项目目录。后续命令必须在包含 `app` 文件夹的目录中执行：

```powershell
Set-Location A:\copilot_home\RAG
```

### 1. 创建虚拟环境

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS 或 Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. 安装 Python 依赖

```powershell
pip install -r requirements.txt
```

### 3. 准备 Ollama 模型

确认 Ollama 服务已经运行，然后下载默认模型：

```powershell
ollama pull nomic-embed-text
ollama pull llama3.2
```

如果使用其他模型，请同步修改 `.env` 中的模型名称。

### 4. 配置环境变量（可选）

复制示例配置：

```powershell
Copy-Item .env.example .env
```

主要配置项如下：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama 服务地址 |
| `OLLAMA_CHAT_MODEL` | `llama3.2` | 用于生成回答的模型 |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | 用于生成向量的模型 |
| `RAG_DATA_DIR` | `./data` | 上传文件和 Chroma 索引的保存目录 |
| `CHUNK_SIZE` | `800` | 文本分块大小 |
| `CHUNK_OVERLAP` | `120` | 相邻文本块的重叠大小 |
| `TOP_K` | `4` | 每次问答检索的文本块数量 |

### 5. 启动应用

```powershell
python -m uvicorn app.main:app --reload
```

启动后打开 <http://127.0.0.1:8000>，即可上传文档并提问。

## 使用流程

1. 在“导入文档”区域选择 PDF、DOCX、Markdown 或 TXT 文件。
2. 点击“导入并建立索引”，等待文档处理完成。
3. 在“索引状态”区域查看已导入文档和文本块数量。
4. 在“问答”区域输入问题并提交。
5. 查看回答及其引用的来源文件。
6. 如果修改了分块配置或索引状态异常，可点击“重建索引”重新建立索引。

### 修改 RAG 数据库保存位置

在页面的“RAG 数据库位置”区域输入运行应用的电脑上的目录，例如：

```text
A:\rag-data
```

点击“保存位置”后，后续导入的文档会保存到该目录下的 `uploads` 子目录，Chroma 向量索引会保存到 `chroma` 子目录。页面的索引状态区域会显示当前实际使用的绝对路径。切换目录不会自动移动旧目录中的数据；如需继续使用旧索引，请切回旧目录。

## 项目结构

```text
.
├── app/
│   ├── config.py       # 环境变量和应用配置
│   ├── documents.py    # 文档读取和文本分块
│   ├── errors.py       # 用户可见的业务错误
│   ├── main.py         # FastAPI 路由和 Web 页面
│   ├── ollama.py       # Ollama API 客户端
│   └── store.py        # Chroma 索引和检索
├── tests/              # 单元测试
├── data/               # 运行时生成的上传文件和索引
├── .env.example        # 配置示例
└── requirements.txt    # Python 依赖
```

## 运行测试

运行全部测试：

```powershell
python -m pytest -q
```

运行编译检查：

```powershell
python -m compileall -q app tests
```

## API 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | Web 页面 |
| `GET` | `/api/status` | 查看索引状态和模型配置 |
| `POST` | `/api/settings/data-dir` | 切换 RAG 文档和 Chroma 索引保存目录 |
| `POST` | `/api/documents` | 上传并索引文档 |
| `POST` | `/api/rebuild` | 重建全部文档索引 |
| `POST` | `/api/ask` | 根据已索引文档进行问答 |

## 故障排查

### Ollama 无法连接

确认 Ollama 已启动，并检查地址：

```powershell
ollama list
```

如需使用远程 Ollama 服务，请设置：

```text
OLLAMA_BASE_URL=http://服务器地址:11434
```

### 模型缺失

根据错误提示下载缺失模型，例如：

```powershell
ollama pull llama3.2
ollama pull nomic-embed-text
```

### 找不到 `app` 模块

如果看到以下错误：

```text
ModuleNotFoundError: No module named 'app'
```

通常是因为当前终端不在项目目录。请先执行：

```powershell
Set-Location A:\copilot_home\RAG
python -m uvicorn app.main:app --reload
```

也可以不切换目录，直接指定应用目录：

```powershell
python -m uvicorn --app-dir A:\copilot_home\RAG app.main:app --reload
```

### 文档重复导入

应用会根据文件内容计算唯一标识。同一份内容重复上传时会提示已经导入，不会重复写入索引。

### `/api/ask` 返回 400

当问题为空或只包含空格时，接口会返回 HTTP 400，这是输入校验，不是服务故障。请先在问答框输入问题。页面会在发送请求前直接提示“请输入问题后再提问”，不会再发送空问题请求。

### 数据目录

默认情况下，上传文件和 Chroma 数据保存在 `data/` 目录。该目录已加入 `.gitignore`，不会被提交到版本库。
