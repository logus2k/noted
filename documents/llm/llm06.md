# Local LLM Integration Design Document for noted MLOps Platform

## 1. Overview and Requirements

### 1.1 Current Context
noted is a comprehensive MLOps platform that already integrates:
- Interactive notebooks (Jupyter-compatible)
- MLflow for experiment tracking
- DVC + MinIO for data versioning
- Hydra for configuration management
- Airflow for pipeline orchestration
- Model registry and serving

The platform currently has a chat panel with an external LLM agent, but lacks integrated local LLM capabilities.

### 1.2 Goals
Integrate a local LLM assistant that provides:
- Code generation, completion, and explanation in notebooks and Python files
- Natural language interaction for MLOps operations (e.g., "create an experiment tracking config")
- Context-aware assistance using project structure, active notebook content, and MLOps metadata
- On-premises deployment without external API dependencies
- Optional GPU acceleration for LLM inference

### 1.3 Key Requirements
- **Privacy**: All processing remains on-premises
- **Performance**: Acceptable latency for interactive use (sub-500ms for simple completions)
- **Resource efficiency**: Support both CPU-only and GPU deployments
- **Integration**: Seamless with existing noted architecture
- **Extensibility**: Support for multiple model backends (Llama, Mistral, etc.)

---

## 2. Architecture Patterns

### 2.1 Service Separation Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                        noted (Main Container)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Frontend   │  │   Backend    │  │   LLM Service    │  │
│  │   (ES6)      │◄─┤  (FastAPI)   │◄─┤    Container     │  │
│  │              │  │              │  │                  │  │
│  │ - Chat UI    │  │ - Auth       │  │ - Model Loading │  │
│  │ - Context    │  │ - Routing    │  │ - Inference     │  │
│  │   Collection │  │ - Streaming  │  │ - Caching       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Rationale**: Separate LLM inference into its own container to:
- Isolate heavy dependencies (PyTorch, transformers, CUDA)
- Enable independent scaling and restart without affecting core platform
- Allow GPU allocation control
- Maintain single responsibility principle

### 2.2 Context Aggregation Pattern

```python
class ContextAggregator:
    """
    Collects and structures context from various noted components
    for LLM prompts.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.context_sources = {
            'active_file': None,
            'project_structure': None,
            'mlflow_context': None,
            'hydra_config': None,
            'airflow_context': None,
            'data_versions': None
        }
    
    async def gather_context(self, request_type: str) -> dict:
        """
        Request types: 'code_completion', 'explanation', 'mlops_command'
        """
        context = {}
        
        # Active notebook/cell content
        context['active_content'] = await self._get_active_content()
        
        # Project context (from workspace tree)
        context['project'] = await self._get_project_context()
        
        # MLOps context based on request type
        if request_type == 'mlops_command':
            context['experiments'] = await self._get_recent_experiments()
            context['models'] = await self._get_registered_models()
            context['pipelines'] = await self._get_pipelines()
            
        return context
```

### 2.3 Prompt Engineering Pattern

```python
class PromptBuilder:
    """
    Builds structured prompts with system instructions and context.
    """
    SYSTEM_PROMPTS = {
        'code': """You are a coding assistant for MLOps tasks. 
        You have access to the user's current notebook/code and project context.
        Provide concise, actionable code with explanations.""",
        
        'mlops': """You are an MLOps assistant helping with experiment tracking,
        pipeline orchestration, and model management. Use the provided context
        about existing experiments, models, and pipelines."""
    }
    
    def build_prompt(self, user_query: str, context: dict, request_type: str) -> str:
        prompt_parts = [
            self.SYSTEM_PROMPTS[request_type],
            "\n\n## Current Context:\n"
        ]
        
        # Add relevant context sections
        if context.get('active_content'):
            prompt_parts.append(f"Current code:\n```python\n{context['active_content']}\n```")
        
        if context.get('experiments'):
            prompt_parts.append(f"Recent experiments: {context['experiments'][:3]}")
            
        if context.get('models'):
            prompt_parts.append(f"Registered models: {context['models'][:3]}")
            
        prompt_parts.append(f"\n## User Request:\n{user_query}")
        
        return "\n".join(prompt_parts)
```

---

## 3. Implementation Details

### 3.1 LLM Service Container

Create `services/llm-service/Dockerfile`:

```dockerfile
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install transformers and inference engine
RUN pip install transformers accelerate bitsandbytes sentencepiece

# Copy service code
COPY . .

# Download model on build (optional, can be volume-mounted)
RUN python download_model.py --model ${LLM_MODEL:-meta-llama/Llama-2-7b-chat-hf}

EXPOSE 8124

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8124"]
```

`services/llm-service/requirements.txt`:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
transformers==4.35.0
torch==2.1.0
accelerate==0.25.0
bitsandbytes==0.41.1
sentencepiece==0.1.99
```

### 3.2 LLM Service Core Implementation

`services/llm-service/main.py`:

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, AsyncGenerator, List
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import asyncio
import logging

app = FastAPI(title="noted LLM Service")

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.95
    stream: bool = False
    
class GenerateResponse(BaseModel):
    text: str
    usage: dict = Field(default_factory=dict)

class LLMService:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
    async def load_model(self, model_name: str = "meta-llama/Llama-2-7b-chat-hf"):
        """Load model with quantization if needed."""
        if self.model is not None:
            return
            
        logging.info(f"Loading model {model_name} on {self.device}")
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.tokenizer.pad_token = self.tokenizer.eos_token
        
        # Load model with appropriate settings
        if self.device.type == "cuda":
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float16,
                device_map="auto",
                load_in_8bit=True,  # Quantization for 8GB+ GPUs
                trust_remote_code=True
            )
        else:
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float32,
                trust_remote_code=True
            )
            self.model = self.model.to(self.device)
        
        self.model.eval()
        logging.info("Model loaded successfully")
    
    async def generate(self, request: GenerateRequest) -> str:
        """Generate text from prompt."""
        if self.model is None:
            await self.load_model()
            
        # Tokenize input
        inputs = self.tokenizer(
            request.prompt, 
            return_tensors="pt", 
            truncation=True, 
            max_length=4096 - request.max_tokens
        ).to(self.device)
        
        # Generate
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                do_sample=True,
                pad_token_id=self.tokenizer.pad_token_id
            )
        
        # Decode
        response = self.tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1]:], 
            skip_special_tokens=True
        )
        
        return response
    
    async def generate_stream(self, request: GenerateRequest) -> AsyncGenerator[str, None]:
        """Stream tokens as they're generated."""
        if self.model is None:
            await self.load_model()
            
        inputs = self.tokenizer(
            request.prompt, 
            return_tensors="pt", 
            truncation=True, 
            max_length=4096 - request.max_tokens
        ).to(self.device)
        
        # Streaming generation
        generated_tokens = []
        with torch.no_grad():
            for _ in range(request.max_tokens):
                outputs = self.model.generate(
                    inputs.input_ids if not generated_tokens else torch.cat([inputs.input_ids, generated_tokens], dim=1),
                    max_new_tokens=1,
                    temperature=request.temperature,
                    do_sample=True
                )
                
                new_token = outputs[0, -1:]
                generated_tokens.append(new_token)
                
                token_text = self.tokenizer.decode(new_token, skip_special_tokens=True)
                yield f"data: {token_text}\n\n"
                
                if new_token.item() == self.tokenizer.eos_token_id:
                    break
                
                await asyncio.sleep(0.01)  # Allow for streaming backpressure

llm_service = LLMService()

@app.on_event("startup")
async def startup_event():
    """Pre-load model on startup."""
    await llm_service.load_model()

@app.post("/generate")
async def generate(request: GenerateRequest):
    """Non-streaming generation."""
    try:
        text = await llm_service.generate(request)
        return GenerateResponse(text=text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate/stream")
async def generate_stream(request: GenerateRequest):
    """Streaming generation."""
    try:
        return StreamingResponse(
            llm_service.generate_stream(request),
            media_type="text/event-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model_loaded": llm_service.model is not None,
        "device": str(llm_service.device)
    }
```

### 3.3 Backend Integration

`backend/app/llm/client.py`:

```python
import httpx
from typing import Optional, AsyncGenerator
import logging
from pydantic import BaseModel

class LLMClient:
    def __init__(self, base_url: str = "http://noted-llm:8124"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)
        
    async def generate(
        self, 
        prompt: str, 
        max_tokens: int = 512,
        temperature: float = 0.7,
        stream: bool = False
    ) -> Optional[str]:
        """Send generation request to LLM service."""
        try:
            if stream:
                return await self._stream_generate(prompt, max_tokens, temperature)
            else:
                response = await self.client.post(
                    f"{self.base_url}/generate",
                    json={
                        "prompt": prompt,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "stream": False
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data["text"]
        except Exception as e:
            logging.error(f"LLM generation failed: {e}")
            return None
            
    async def _stream_generate(
        self, 
        prompt: str, 
        max_tokens: int,
        temperature: float
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from LLM service."""
        async with self.client.stream(
            "POST",
            f"{self.base_url}/generate/stream",
            json={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True
            }
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    yield line[6:]
```

`backend/app/routers/llm.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.responses import StreamingResponse
from typing import Optional
from app.llm.client import LLMClient
from app.llm.context import ContextAggregator
from app.llm.prompt_builder import PromptBuilder
from app.auth import get_current_user

router = APIRouter(prefix="/api/llm", tags=["llm"])
llm_client = LLMClient()

@router.post("/chat")
async def chat(
    message: str,
    request_type: str = "code",
    context: Optional[dict] = None,
    user = Depends(get_current_user)
):
    """Process chat message with context."""
    # Gather context if not provided
    if not context:
        context_aggregator = ContextAggregator(user.id)
        context = await context_aggregator.gather_context(request_type)
    
    # Build prompt
    prompt_builder = PromptBuilder()
    full_prompt = prompt_builder.build_prompt(message, context, request_type)
    
    # Generate response
    response = await llm_client.generate(
        prompt=full_prompt,
        max_tokens=512,
        temperature=0.7
    )
    
    return {"response": response}

@router.post("/chat/stream")
async def chat_stream(
    message: str,
    request_type: str = "code",
    user = Depends(get_current_user)
):
    """Streaming chat response."""
    context_aggregator = ContextAggregator(user.id)
    context = await context_aggregator.gather_context(request_type)
    
    prompt_builder = PromptBuilder()
    full_prompt = prompt_builder.build_prompt(message, context, request_type)
    
    return StreamingResponse(
        llm_client._stream_generate(full_prompt, 512, 0.7),
        media_type="text/event-stream"
    )

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for real-time assistance."""
    await websocket.accept()
    
    while True:
        try:
            data = await websocket.receive_json()
            message = data.get("message")
            request_type = data.get("type", "code")
            
            # Process message and stream response
            await websocket.send_json({"status": "processing"})
            
            async for token in llm_client._stream_generate(message, 512, 0.7):
                await websocket.send_json({"token": token})
            
            await websocket.send_json({"status": "complete"})
        except Exception as e:
            await websocket.send_json({"error": str(e)})
```

### 3.4 Frontend Integration

`frontend/js/llm/chat-panel.js`:

```javascript
export class LLMChatPanel {
    constructor() {
        this.ws = null;
        this.messageHistory = [];
        this.contextCache = {};
        this.initUI();
        this.connectWebSocket();
    }
    
    initUI() {
        // Create chat panel UI
        this.container = document.createElement('div');
        this.container.className = 'llm-chat-panel';
        this.container.innerHTML = `
            <div class="chat-header">
                <h3>AI Assistant</h3>
                <div class="chat-controls">
                    <select id="assistant-mode">
                        <option value="code">Code Assistant</option>
                        <option value="mlops">MLOps Assistant</option>
                        <option value="general">General Assistant</option>
                    </select>
                    <button id="clear-chat">Clear</button>
                </div>
            </div>
            <div class="chat-messages" id="chat-messages"></div>
            <div class="chat-input-area">
                <textarea id="chat-input" placeholder="Ask me anything about your code or MLOps..." rows="3"></textarea>
                <button id="send-message">Send</button>
            </div>
            <div class="context-indicator">
                <span>Context: </span>
                <span id="context-summary">Active notebook: main.ipynb</span>
            </div>
        `;
        
        // Add to existing chat panel in noted
        const chatContainer = document.querySelector('.chat-panel');
        if (chatContainer) {
            chatContainer.appendChild(this.container);
        }
        
        // Bind events
        this.bindEvents();
    }
    
    connectWebSocket() {
        const wsUrl = `ws://${window.location.host}/api/llm/ws`;
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.token) {
                this.appendToken(data.token);
            } else if (data.status === 'complete') {
                this.messageComplete();
            } else if (data.error) {
                this.showError(data.error);
            }
        };
    }
    
    async sendMessage() {
        const input = document.getElementById('chat-input');
        const message = input.value.trim();
        if (!message) return;
        
        const mode = document.getElementById('assistant-mode').value;
        
        // Add user message to chat
        this.addMessage('user', message);
        input.value = '';
        
        // Show typing indicator
        this.showTypingIndicator();
        
        // Send via WebSocket
        this.ws.send(JSON.stringify({
            message: message,
            type: mode
        }));
    }
    
    async gatherContext() {
        // Collect active notebook content
        const activeNotebook = await this.getActiveNotebook();
        
        // Collect current selection
        const selection = await this.getCurrentSelection();
        
        // Collect project context
        const project = await this.getCurrentProject();
        
        return {
            active_notebook: activeNotebook,
            selection: selection,
            project: project,
            experiments: await this.getRecentExperiments(),
            models: await this.getRegisteredModels()
        };
    }
    
    async getActiveNotebook() {
        // Get active notebook from notebook manager
        const notebookManager = window.notebookManager;
        if (notebookManager && notebookManager.activeNotebook) {
            return {
                name: notebookManager.activeNotebook.name,
                content: await notebookManager.getCellContent(notebookManager.activeCellIndex)
            };
        }
        return null;
    }
    
    async getCurrentSelection() {
        // Get selected text in active editor
        const activeEditor = this.getActiveEditor();
        if (activeEditor && activeEditor.getSelection) {
            return activeEditor.getSelection();
        }
        return '';
    }
    
    addMessage(role, content) {
        const messagesContainer = document.getElementById('chat-messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${role}`;
        
        const timestamp = new Date().toLocaleTimeString();
        
        if (role === 'assistant') {
            messageDiv.innerHTML = `
                <div class="message-header">
                    <span class="message-role">AI Assistant</span>
                    <span class="message-time">${timestamp}</span>
                </div>
                <div class="message-content">${this.formatContent(content)}</div>
                <div class="message-actions">
                    <button class="copy-response">Copy</button>
                    <button class="insert-to-notebook">Insert to Notebook</button>
                </div>
            `;
            
            // Add action handlers
            const copyBtn = messageDiv.querySelector('.copy-response');
            copyBtn?.addEventListener('click', () => this.copyToClipboard(content));
            
            const insertBtn = messageDiv.querySelector('.insert-to-notebook');
            insertBtn?.addEventListener('click', () => this.insertToNotebook(content));
        } else {
            messageDiv.innerHTML = `
                <div class="message-header">
                    <span class="message-role">You</span>
                    <span class="message-time">${timestamp}</span>
                </div>
                <div class="message-content">${this.formatContent(content)}</div>
            `;
        }
        
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        this.messageHistory.push({role, content, timestamp});
    }
    
    formatContent(content) {
        // Format code blocks with syntax highlighting
        return content.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
            return `<pre><code class="language-${lang || 'text'}">${this.escapeHtml(code)}</code></pre>`;
        });
    }
    
    insertToNotebook(content) {
        // Extract code blocks from response
        const codeBlocks = content.match(/```(?:\w+)?\n([\s\S]*?)```/g);
        
        if (codeBlocks && codeBlocks.length > 0) {
            // Insert first code block into notebook
            const code = codeBlocks[0].replace(/```\w*\n/, '').replace(/```$/, '');
            
            const notebookManager = window.notebookManager;
            if (notebookManager && notebookManager.activeNotebook) {
                notebookManager.insertCell('code', code);
                this.showNotification('Code inserted into notebook');
            }
        } else {
            // Insert as markdown
            const notebookManager = window.notebookManager;
            if (notebookManager && notebookManager.activeNotebook) {
                notebookManager.insertCell('markdown', content);
                this.showNotification('Response inserted as markdown');
            }
        }
    }
    
    copyToClipboard(text) {
        navigator.clipboard.writeText(text);
        this.showNotification('Copied to clipboard');
    }
    
    showNotification(message) {
        // Use existing notification system (Notyf)
        if (window.notyf) {
            window.notyf.success(message);
        }
    }
    
    showTypingIndicator() {
        const messagesContainer = document.getElementById('chat-messages');
        const indicator = document.createElement('div');
        indicator.className = 'chat-message assistant typing';
        indicator.id = 'typing-indicator';
        indicator.innerHTML = '<div class="message-content">AI is thinking<span>...</span></div>';
        messagesContainer.appendChild(indicator);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.remove();
    }
    
    appendToken(token) {
        this.removeTypingIndicator();
        
        let lastMessage = document.querySelector('.chat-message.assistant:last-child');
        if (!lastMessage || lastMessage.classList.contains('complete')) {
            this.addMessage('assistant', '');
            lastMessage = document.querySelector('.chat-message.assistant:last-child');
            lastMessage.classList.remove('complete');
        }
        
        const contentDiv = lastMessage.querySelector('.message-content');
        contentDiv.innerHTML += token;
    }
    
    messageComplete() {
        const lastMessage = document.querySelector('.chat-message.assistant:last-child');
        if (lastMessage) {
            lastMessage.classList.add('complete');
            // Trigger syntax highlighting
            if (window.Prism) {
                Prism.highlightAllUnder(lastMessage);
            }
        }
    }
    
    bindEvents() {
        const sendBtn = document.getElementById('send-message');
        const input = document.getElementById('chat-input');
        
        sendBtn?.addEventListener('click', () => this.sendMessage());
        input?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        const clearBtn = document.getElementById('clear-chat');
        clearBtn?.addEventListener('click', () => {
            const messagesContainer = document.getElementById('chat-messages');
            messagesContainer.innerHTML = '';
            this.messageHistory = [];
        });
    }
}
```

### 3.5 Context Integration for MLOps

`backend/app/llm/context.py`:

```python
from typing import Optional, Dict, Any
import mlflow
from mlflow.tracking import MlflowClient
from app.services.airflow import AirflowClient
from app.services.dvc import DVCManager
from app.services.hydra import HydraManager

class ContextAggregator:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.mlflow_client = MlflowClient()
        self.airflow_client = AirflowClient()
        self.dvc_manager = DVCManager()
        self.hydra_manager = HydraManager()
        
    async def gather_context(self, request_type: str) -> Dict[str, Any]:
        """Gather context based on request type."""
        context = {
            'active_file': await self._get_active_file(),
            'project': await self._get_project_context(),
            'timestamp': datetime.now().isoformat()
        }
        
        if request_type == 'code':
            context['code_context'] = await self._get_code_context()
            
        elif request_type == 'mlops':
            context.update(await self._get_mlops_context())
            
        elif request_type == 'pipeline':
            context.update(await self._get_pipeline_context())
            
        return context
    
    async def _get_mlops_context(self) -> Dict[str, Any]:
        """Gather MLOps-specific context."""
        context = {}
        
        # Get recent experiments
        try:
            experiments = self.mlflow_client.search_experiments(
                max_results=5
            )
            context['experiments'] = [
                {
                    'name': exp.name,
                    'artifact_location': exp.artifact_location,
                    'tags': exp.tags
                }
                for exp in experiments
            ]
        except Exception:
            context['experiments'] = []
            
        # Get registered models
        try:
            models = self.mlflow_client.search_registered_models(
                max_results=5
            )
            context['models'] = [
                {
                    'name': model.name,
                    'latest_versions': [
                        {'version': v.version, 'stage': v.stage}
                        for v in model.latest_versions
                    ]
                }
                for model in models
            ]
        except Exception:
            context['models'] = []
            
        # Get DVC-tracked files
        try:
            dvc_files = self.dvc_manager.list_tracked_files()
            context['data_files'] = [
                {
                    'path': f['path'],
                    'hash': f['md5'],
                    'size': f['size']
                }
                for f in dvc_files[:10]
            ]
        except Exception:
            context['data_files'] = []
            
        return context
    
    async def _get_pipeline_context(self) -> Dict[str, Any]:
        """Gather Airflow pipeline context."""
        context = {}
        
        try:
            # Get DAGs and recent runs
            dags = await self.airflow_client.get_dags()
            context['pipelines'] = []
            
            for dag in dags[:5]:
                runs = await self.airflow_client.get_dag_runs(dag['dag_id'], limit=3)
                context['pipelines'].append({
                    'name': dag['dag_id'],
                    'is_active': dag['is_active'],
                    'recent_runs': [
                        {
                            'run_id': run['run_id'],
                            'state': run['state'],
                            'start_date': run.get('start_date')
                        }
                        for run in runs
                    ]
                })
        except Exception:
            context['pipelines'] = []
            
        return context
    
    async def _get_code_context(self) -> Dict[str, Any]:
        """Gather code-specific context."""
        context = {}
        
        # Get active file's imports and functions
        active_file = await self._get_active_file()
        if active_file and active_file.get('content'):
            context['imports'] = self._extract_imports(active_file['content'])
            context['functions'] = self._extract_functions(active_file['content'])
            
        return context
    
    def _extract_imports(self, content: str) -> list:
        """Extract import statements from code."""
        import re
        imports = []
        
        # Match import lines
        import_pattern = r'^(?:from\s+(\S+)\s+import\s+(\S+)|import\s+(\S+))'
        for line in content.split('\n'):
            match = re.match(import_pattern, line)
            if match:
                if match.group(1):  # from ... import ...
                    imports.append(f"from {match.group(1)} import {match.group(2)}")
                elif match.group(3):  # import ...
                    imports.append(f"import {match.group(3)}")
                    
        return imports
    
    def _extract_functions(self, content: str) -> list:
        """Extract function definitions from code."""
        import re
        function_pattern = r'^def\s+(\w+)\s*\((.*?)\):'
        functions = []
        
        for line in content.split('\n'):
            match = re.match(function_pattern, line)
            if match:
                functions.append({
                    'name': match.group(1),
                    'params': match.group(2)
                })
                
        return functions
```

---

## 4. Docker Compose Integration

Add to `services/docker-compose.yml`:

```yaml
services:
  # Existing services...
  
  noted-llm:
    build:
      context: ./llm-service
      dockerfile: Dockerfile
    image: noted-llm:latest
    container_name: noted-llm
    restart: unless-stopped
    ports:
      - "8124:8124"
    environment:
      - LLM_MODEL=${LLM_MODEL:-meta-llama/Llama-2-7b-chat-hf}
      - MODEL_CACHE_DIR=/models
      - CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
    volumes:
      - noted_llm_models:/models
      - ../data/llm_cache:/app/cache
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    networks:
      - noted-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8124/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Optional: Ollama service for alternative model backend
  noted-ollama:
    image: ollama/ollama:latest
    container_name: noted-ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - noted_ollama_models:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    networks:
      - noted-network

volumes:
  noted_llm_models:
  noted_ollama_models:
```

---

## 5. Environment Configuration

Add to `.env`:

```bash
# LLM Configuration
LLM_MODEL=meta-llama/Llama-2-7b-chat-hf
LLM_BACKEND=transformers  # or 'ollama'
LLM_MAX_TOKENS=512
LLM_TEMPERATURE=0.7
LLM_GPU_LAYERS=28  # For llama.cpp backend

# Ollama specific (if using)
OLLAMA_HOST=http://noted-ollama:11434
OLLAMA_MODEL=llama2:7b

# Model cache
MODEL_CACHE_DIR=/models
MODEL_CACHE_SIZE=50GB

# GPU allocation
CUDA_VISIBLE_DEVICES=0  # Use first GPU
```

---

## 6. Performance Optimization Patterns

### 6.1 Model Quantization

```python
# In LLMService.load_model()
def load_quantized_model(self, model_name: str, quantization: str = "8bit"):
    """Load quantized model for memory efficiency."""
    if self.device.type == "cuda":
        if quantization == "8bit":
            return AutoModelForCausalLM.from_pretrained(
                model_name,
                load_in_8bit=True,
                device_map="auto"
            )
        elif quantization == "4bit":
            return AutoModelForCausalLM.from_pretrained(
                model_name,
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                device_map="auto"
            )
    return AutoModelForCausalLM.from_pretrained(model_name)
```

### 6.2 Response Caching

```python
from functools import lru_cache
from hashlib import sha256

class ResponseCache:
    def __init__(self, max_size: int = 100):
        self.cache = {}
        self.max_size = max_size
        
    def get_cache_key(self, prompt: str, temperature: float) -> str:
        """Generate cache key from prompt and temperature."""
        content = f"{prompt}:{temperature}"
        return sha256(content.encode()).hexdigest()
    
    async def get_cached(self, key: str) -> Optional[str]:
        """Get cached response if exists."""
        return self.cache.get(key)
    
    async def cache_response(self, key: str, response: str):
        """Cache response, managing size."""
        if len(self.cache) >= self.max_size:
            # Remove oldest
            oldest = next(iter(self.cache))
            del self.cache[oldest]
        self.cache[key] = response
```

### 6.3 Batch Processing

```python
class BatchProcessor:
    """Process multiple prompts in batch for efficiency."""
    def __init__(self, llm_service, batch_size: int = 4):
        self.llm = llm_service
        self.batch_size = batch_size
        self.queue = asyncio.Queue()
        
    async def process_batch(self):
        """Process queued prompts in batch."""
        while True:
            batch = []
            for _ in range(self.batch_size):
                try:
                    item = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                    batch.append(item)
                except asyncio.TimeoutError:
                    break
                    
            if batch:
                # Process batch together
                prompts = [item['prompt'] for item in batch]
                # Implementation depends on model API
                responses = await self.llm.generate_batch(prompts)
                
                # Return responses to callers
                for item, response in zip(batch, responses):
                    item['future'].set_result(response)
```

---

## 7. Security Considerations

### 7.1 API Authentication

```python
# backend/app/llm/auth.py
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_llm_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    """Verify token for LLM service access."""
    token = credentials.credentials
    
    # Validate against noted's internal auth
    if not await validate_internal_token(token):
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials"
        )
    
    return token
```

### 7.2 Input Sanitization

```python
def sanitize_prompt(prompt: str) -> str:
    """Sanitize user input to prevent injection."""
    import re
    
    # Remove potential injection patterns
    prompt = re.sub(r'[\x00-\x08\x0b\x0c\x0
