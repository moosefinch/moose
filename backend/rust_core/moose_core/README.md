# Moose Core - Rust Backend

High-performance Rust implementation of performance-critical components for the Moose AI backend.

## Components

### Vector Memory Engine (`vector.rs`)
- SIMD-accelerated cosine similarity search via ndarray
- Pre-normalized vectors for efficient search
- Connection pooling for embedding HTTP requests
- JSONL persistence with auto-eviction

### Episodic Memory (`episodic.rs`)
- SQLite-backed persistence with WAL mode
- Vector similarity search with importance weighting
- Automatic importance decay over time
- Entity supersession for knowledge updates

### GPU Scheduler (`scheduler.rs`)
- Event-driven dispatch (replaces 50ms polling)
- Lock-free mission state with DashMap
- Dependency-level task grouping
- Integration with MessageBus

### Inference Router (`router.rs` + adapters)
- Multiple backend support (LlamaCpp, Ollama, OpenAI-compatible)
- Model key mapping (primary, classifier, security, embedder)
- Semaphore-based slot management
- Streaming support with channels

## Building

### Prerequisites
- Rust 1.70+ (install via [rustup](https://rustup.rs/))
- Python 3.10+
- maturin (`pip install maturin`)

### Development Build
```bash
cd backend/rust_core
maturin develop --release
```

### Production Build
```bash
cd backend/rust_core
maturin build --release
pip install target/wheels/moose_core-*.whl
```

## Usage

### Python Integration

```python
# Vector Memory
from rust_memory import VectorMemory

memory = VectorMemory()
memory.set_embedder("http://localhost:1234", "text-embedding-model")
await memory.store("Hello world", tags="greeting,test")
results = await memory.search("Hello", top_k=5)

# Episodic Memory
from rust_episodic import EpisodicMemory

episodic = EpisodicMemory("path/to/db.sqlite")
await episodic.store("Important fact", memory_type="fact", importance=0.9)
results = await episodic.search("fact query", top_k=10)
episodic.decay_importance(decay_rate=0.05)

# Scheduler
from rust_scheduler import Scheduler, MessageBus

bus = MessageBus()
scheduler = Scheduler(poll_interval_ms=50)
scheduler.set_message_bus(bus)
scheduler.submit_mission("mission-1", tasks=[...])
result = await scheduler.await_mission("mission-1", timeout=300)

# Inference Router
from rust_router import InferenceRouter

router = InferenceRouter()
router.initialize({
    "backends": {
        "local": {
            "type": "llamacpp",
            "base_url": "http://localhost:8080",
        }
    },
    "models": {
        "primary": {"backend": "local", "model_id": "llama3"},
    }
})
response = await router.call_llm("primary", messages=[{"role": "user", "content": "Hello"}])
```

## Testing

```bash
# Run Rust tests
cd backend/rust_core
cargo test

# Run Python integration tests
python -m pytest tests/test_rust_*.py -v
```

## Benchmarks

```bash
# Run benchmarks
python -m pytest tests/bench_rust_vs_python.py -v
```

## Architecture

```
rust_core/
├── Cargo.toml               # Workspace manifest
├── moose_core/
│   ├── Cargo.toml           # Crate manifest
│   ├── pyproject.toml       # Maturin config
│   └── src/
│       ├── lib.rs           # PyO3 module exports
│       ├── vector.rs        # Vector memory engine
│       ├── episodic.rs      # Episodic memory
│       ├── scheduler.rs     # GPU scheduler
│       ├── router.rs        # Inference router
│       ├── messages.rs      # Message bus
│       ├── workspace.rs     # Shared workspace
│       └── adapters/
│           ├── mod.rs       # InferenceBackend trait
│           ├── llamacpp.rs  # llama.cpp adapter
│           ├── ollama.rs    # Ollama adapter
│           └── openai.rs    # OpenAI-compatible adapter
```

## License

MIT
