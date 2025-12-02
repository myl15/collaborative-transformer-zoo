# Collaborative Transformer Zoo - AI Agent Instructions

## Project Overview
A FastAPI web platform for interactive visualization of transformer model internals. Users submit text and a model name, view attention patterns via BertViz, and permanently store visualizations in PostgreSQL with shareable URLs.

**Key Stack:** FastAPI, SQLModel (ORM), PostgreSQL, PyTorch, BertViz, HuggingFace Transformers

## Architecture & Data Flow

### Core Components
1. **main.py** - FastAPI server with three endpoints:
   - `GET /` - Home form (model name, input text, view type selection)
   - `POST /visualize` - Generates viz HTML via `get_viz_data()`, stores in DB, redirects to persistent URL
   - `GET /viz/{id}` - Retrieves stored visualization with view-switching UI

2. **visualization_logic.py** - GPU/ML operations:
   - `load_model_smart()` - Global `MODEL_CACHE` dict prevents reloading same model; swaps models intelligently
   - `check_model_size()` - Queries HuggingFace API before loading; enforces 6GB limit
   - `get_viz_data()` - Tokenizes input (max 50 tokens), runs model with `output_attentions=True`, generates BertViz HTML
   - Supports both encoder-decoder (T5-like) and causal (GPT-like) models
   - `free_memory()` - Moves model to CPU, deletes from cache, calls `gc.collect()` and `torch.cuda.empty_cache()`

3. **database.py** - Connection & schema management:
   - PostgreSQL connection via SQLAlchemy/SQLModel
   - `create_db_and_tables()` called on server startup (lifespan context manager)

4. **models.py** - Single SQLModel table:
   - `Visualization` stores: model_name, input_text, view_type, full HTML content, created_at timestamp

### Deployment Dependencies
- **Docker:** `docker-compose.yml` spins up PostgreSQL 15 container (port 5432)
- **Environment:** `.env` file required with `HF_TOKEN=<your_huggingface_token>` for gated models
- **GPU Support:** Auto-detects CUDA, Apple Metal (MPS), or CPU via `torch` checks

## Critical Workflows

### Starting Development
```bash
# Start PostgreSQL container (required before uvicorn)
docker-compose up -d

# Install dependencies
pip install fastapi[standard] sqlmodel transformers torch bertviz huggingface_hub python-dotenv

# Create .env with HuggingFace token
echo "HF_TOKEN=your_token_here" > .env

# Run server (auto-creates tables on startup)
uvicorn main:app --reload
```

### Memory Management Pattern
- **Problem:** LLMs exhaust VRAM; loading different models crashes server
- **Solution:** `load_model_smart()` implements single-model cache; switching models calls `free_memory()` first
- **UI Integration:** `/unload` endpoint clears cache before returning home (user can manually free VRAM)
- **Key Detail:** Always move tensors to CPU before deletion to clear VRAM, not just RAM

### Visualization Rendering
- BertViz renders attention matrices as interactive HTML with d3.js
- Two view types: `head` (attention head detail) vs `model` (layer-wise blocks)
- HTML stored as string in database (not as file); loaded directly into page with `{viz.html_content}` template injection

## Project-Specific Conventions

### Model Type Handling
- Check `config.is_encoder_decoder` to determine if T5-like or GPT-like
- Encoder-decoder models have separate encoder/decoder/cross attention; causal models have single attention stack
- Always pass `output_attentions=True` when loading model

### Error Handling
- HTTP 401/403 from HF API → model is gated (user/token must accept license)
- Size check validates model before loading (query HF API, sum safetensors/bin files)
- Truncation to 50 tokens prevents OOM on very long inputs

### Database Interaction
- Use SQLModel dependency injection: `session: Session = Depends(get_session)`
- Always call `session.refresh(viz)` after `session.commit()` to get auto-incremented ID
- Visualization ID becomes the permanent shareable URL

## Key Files by Purpose
- **models.py** - Single table schema; extend here for annotations feature
- **visualization_logic.py** - All GPU/model logic; update `load_model_smart()` if caching strategy changes
- **database.py** - Connection string & lifecycle; credentials from `DATABASE_URL` (hardcoded for now, move to `.env`)
- **main.py** - HTTP layer only; keep routing logic minimal, defer to helper modules

## Next Steps (From Project Instructions)
- **Week 2:** Database schema + save/view (✓ mostly done, add user authentication)
- **Week 3:** Add Annotations table; implement collaborative commenting feature
- **Week 4:** Redis caching layer; finalize demo
