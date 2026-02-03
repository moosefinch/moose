# Deployment Guide

## Prerequisites

- **Python**: 3.11 or higher
- **Node.js**: 18 or higher
- **Rust**: Latest stable (optional, for Rust core components)
- **LM Studio**: Running locally (default: http://127.0.0.1:1234)

## Quick Start (Development)

### Backend

```bash
cd backend
pip install -r requirements.txt
python main.py
```

The backend starts on `http://127.0.0.1:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend starts on `http://localhost:3000`.

## Production Deployment

### Backend

```bash
cd backend
pip install -r requirements.txt

# Run with multiple workers
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Frontend

```bash
cd frontend
npm ci
npm run build

# Serve dist/ via nginx or let FastAPI serve it (built-in)
```

### Reverse Proxy (nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name moose.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Building Rust Components (Optional)

```bash
cd backend/rust_core

# Build release version
cargo build --release

# The Python extension will be available for import
```

## Configuration

Copy `profile.yaml.example` to `profile.yaml` and configure:

```yaml
system:
  name: "Your Instance Name"

owner:
  name: "Your Name"

web:
  cors_origins:
    - "https://your-domain.com"

inference:
  api_base: "http://127.0.0.1:1234"  # LM Studio

smtp:
  enabled: false  # Enable for email features
  host: "smtp.example.com"
  # ... other SMTP settings

plugins:
  crm:
    enabled: false
  telegram:
    enabled: false
  slack:
    enabled: false
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MOOSE_API_KEY` | Override auto-generated API key | Auto-generated |
| `PROFILE_PATH` | Custom profile.yaml location | `./profile.yaml` |
| `SMTP_PASSWORD` | SMTP password (recommended over profile) | None |

## API Key Management

### Auto-generated Key

On first run, an API key is auto-generated and stored in `.moose_api_key`:

```bash
cat backend/.moose_api_key
```

### Key Rotation

```bash
# Rotate key (old key valid for 5 minutes)
curl -X POST http://localhost:8000/api/key/rotate \
  -H "X-API-Key: YOUR_CURRENT_KEY"
```

### Key Status

```bash
# Check key age and rotation recommendations
curl http://localhost:8000/api/key/status \
  -H "X-API-Key: YOUR_KEY"
```

## Security Checklist

- [ ] Set strong API key or use auto-generated
- [ ] Configure CORS origins for production domain only
- [ ] Run behind reverse proxy with TLS
- [ ] Ensure `.moose_api_key` has `0600` permissions
- [ ] Store SMTP credentials in environment variables
- [ ] Review and restrict `AGENT_TOOL_FILTER` if needed
- [ ] Enable rate limiting for public endpoints
- [ ] Review CSP headers for your use case

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
# {"status": "ok", "agent_ready": true}
```

### Models Status

```bash
curl http://localhost:8000/api/models \
  -H "X-API-Key: YOUR_KEY"
```

### API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

### WebSocket

Connect to `ws://host:8000/ws` for real-time updates:

```javascript
const ws = new WebSocket("ws://localhost:8000/ws");
ws.onopen = () => {
  ws.send(JSON.stringify({ type: "auth", key: "YOUR_API_KEY" }));
};
```

## macOS Daemon (launchd)

Use the provided plist template:

```bash
# Copy and customize
cp com.moose.backend.plist.template ~/Library/LaunchAgents/com.moose.backend.plist

# Edit paths in the plist file

# Load the daemon
launchctl load ~/Library/LaunchAgents/com.moose.backend.plist
```

## Docker

```bash
# Build
docker build -t moose .

# Run
docker run -p 8000:8000 \
  -v /path/to/profile.yaml:/app/profile.yaml \
  -e MOOSE_API_KEY=your_key \
  moose
```

## Troubleshooting

### "Embedder not configured"

Ensure LM Studio is running with an embedding model loaded (e.g., `nomic-embed-text`).

### "Connection refused" to LLM

Check `inference.api_base` in profile.yaml matches your LM Studio or Ollama endpoint.

### WebSocket connection fails

1. Check CORS origins include your frontend URL
2. Verify API key is correct
3. Check for proxy/firewall blocking WebSocket upgrade

### Tests failing

```bash
# Run with verbose output
pytest backend/tests/ -v --tb=long

# Run specific test file
pytest backend/tests/test_path_validation.py -v
```
