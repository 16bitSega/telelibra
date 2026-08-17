# ⚙️ Telelibra LLM Configuration & Provider Switching Guide

> **💡 QUICK START FOR CLOUD USERS:**  
> Don't want to run heavy local models? You can switch Telelibra to cloud **OpenAI (GPT-4o)** in under 30 seconds!

---

## ⚡ 1. QUICKEST SETUP: Run with OpenAI API Key (Cloud Mode)

If you don't have an Apple Silicon Mac with 24GB RAM or just want instant, cloud-powered synthesis without running local servers:

### Step 1: Open your `.env` file and set:
```ini
# --- Set LLM Provider to OpenAI ---
LLM_PROVIDER=openai
USE_OPENAI=true
OPENAI_API_KEY=sk-proj-your_actual_openai_api_key_here
OPENAI_MODEL=gpt-4o

# --- Vision Settings (uses GPT-4o Vision for screenshots) ---
VISION_ENABLED=true
VISION_PROVIDER=openai
```

### Step 2: Run your ingestion session directly:
```bash
python run_timed_session.py --duration-minutes 30
```
*That’s it! Telelibra will now use GPT-4o for all text analysis, transcript synthesis, and screenshot triage.*

---

## 🍏 2. LOCAL MODE A (Recommended for Mac): Apple Silicon Metal via llama.cpp

For 100% private, zero-cost, local inference on M1/M2/M3/M4/M5 Macs (with 24GB+ Unified Memory):

### Step 1: Start the local Metal server in a separate terminal tab:
```bash
./run_llm_server.sh

# Or enable Speculative Decoding (dflash) for 2x faster token generation:
ENABLE_DFLASH=true ./run_llm_server.sh
```

### Step 2: Configure your `.env`:
```ini
LLM_PROVIDER=llamacpp
LLAMACPP_BASE_URL=http://localhost:8080/v1
LLAMACPP_MODEL_NAME=Muse-Glimmer-30B

VISION_ENABLED=true
VISION_PROVIDER=llamacpp
VISION_MODEL=Muse-Glimmer-30B
VISION_BASE_URL=http://localhost:8080/v1
```

### Step 3: Run your ingestion session:
```bash
python run_timed_session.py --duration-minutes 60
```

---

## 🦙 3. LOCAL MODE B (Cross-Platform): Local Ollama (Mac / Linux / Windows)

If you already use [Ollama](https://ollama.ai) or have 16GB RAM:

### Step 1: Pull and run your model in Ollama:
```bash
ollama run llama3:8b
# or for larger setups:
ollama run qwen2.5:14b
```

### Step 2: Configure your `.env`:
```ini
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b

VISION_ENABLED=true
VISION_PROVIDER=ollama
VISION_MODEL=llama3.2-vision
VISION_BASE_URL=http://localhost:11434
```

---

## 🔌 4. LOCAL MODE C: Custom Local Endpoints (vLLM / LM Studio / SGLang)

If you run LM Studio, vLLM, or text-generation-webui locally:

1. Start your local OpenAI-compatible server (e.g. on port `1234`).
2. Configure your `.env`:
```ini
LLM_PROVIDER=llamacpp
LLAMACPP_BASE_URL=http://localhost:1234/v1
LLAMACPP_MODEL_NAME=your-loaded-model-name
```

---

## 🛡️ Built-in Failover Chain

If your primary local server ever runs out of context or experiences a temporary network interruption, Telelibra features an **automatic fallback chain**:
* If `LLM_PROVIDER=llamacpp` fails, it automatically routes the prompt to **OpenAI** (if `OPENAI_API_KEY` is provided) or **Ollama** before failing, ensuring your ingestion sessions never crash midway.

---

## 📊 Quick Comparison:

| Provider | Setup Effort | Hardware Requirement | Privacy | Speed |
|---|---|---|---|---|
| **OpenAI (`gpt-4o`)** | ⚡ **30 Seconds** (Just paste API key) | Any machine | Cloud API | ⚡⚡ Very Fast |
| **`llama.cpp` (Metal)** | 🛠️ Needs `./run_llm_server.sh` | Mac Apple Silicon (24GB RAM) | 🔒 100% Local | ⚡ Fast (w/ `dflash`) |
| **Ollama** | 🦙 Medium (`ollama run ...`) | Any Mac / Linux / Windows | 🔒 100% Local | ⚡ Fast |
