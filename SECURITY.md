# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.x     | :white_check_mark: |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

To report a security vulnerability:

1. Email the maintainers with:
   - Description of the vulnerability
   - Steps to reproduce
   - Impact assessment
   - Any suggested fixes

2. Allow 48-72 hours for initial response

3. We will work with you to:
   - Confirm the vulnerability
   - Determine severity and impact
   - Develop and test a fix
   - Coordinate disclosure

## Security Architecture

### Authentication

- **API Key Authentication**: All protected endpoints require `X-API-Key` header
- **Key Generation**: Cryptographically secure via `secrets.token_urlsafe(32)` (256-bit entropy)
- **Key Storage**: Stored in `.moose_api_key` with `0600` permissions (owner read/write only)
- **Key Comparison**: Timing-safe comparison via `secrets.compare_digest()`
- **Key Rotation**: `/api/key/rotate` endpoint with 5-minute grace period for old key

### Input Validation

| Input Type | Validation |
|------------|------------|
| **File Paths** | Resolved against project root, symlink detection, blocklist for sensitive files |
| **SQL Queries** | Read-only (SELECT), parameterized queries, dangerous keyword blocklist |
| **Shell Commands** | Allowlist of 30 approved commands, operator blocking (`&&`, `\|`, `;`, etc.) |
| **Memory Tags** | Alphanumeric + underscore/hyphen only, max 20 tags, max 50 chars each |
| **Metadata** | Allowlist of permitted keys only |
| **User Input** | HTML tag stripping, entity encoding |

### Rate Limiting

- **Database-backed**: Persists across restarts
- **Per-IP tracking**: Prevents abuse from single source
- **Configurable limits**: Per endpoint and global

### Security Headers

All responses include:
- `Content-Security-Policy`: Restricts resource loading
- `X-Content-Type-Options: nosniff`: Prevents MIME sniffing
- `X-Frame-Options: DENY`: Prevents clickjacking
- `Referrer-Policy: strict-origin-when-cross-origin`: Controls referrer information

### SSRF Prevention

- Private IP range blocking for web fetch operations
- Hostname resolution before IP validation
- HTTP/HTTPS schemes only

### XSS Prevention (Frontend)

- DOMPurify sanitization on all markdown rendering
- Custom HTML escaping for interpolated content
- Safe link handling with `rel="noopener noreferrer"`

## Network Hardening

### Bind Policy

Moose never binds to `0.0.0.0`. The server resolves its listen address at
startup using this priority:

1. `MOOSE_BIND_HOST` environment variable (explicit override — rejects `0.0.0.0`)
2. Tailscale IPv4 address (via `tailscale ip -4`)
3. `127.0.0.1` fallback (Tailscale not available)

This is implemented in `backend/network.py` and used by both `main.py` (dev)
and `daemon.py` (production).

### Port Map

| Service              | Port  | Allowed Bind      | Notes |
|----------------------|-------|-------------------|-------|
| Moose API            | 8000  | Tailscale IP only | All endpoints including `/v1/` |
| OpenClaw Gateway     | varies| 127.0.0.1         | WebSocket control plane |
| CDP Debug (Chromium) | 9222  | 127.0.0.1         | Must set `--remote-debugging-address=127.0.0.1` |
| Ollama (Bjorn)       | 11434 | 127.0.0.1         | Set `OLLAMA_HOST=127.0.0.1:11434` |
| Ollama (Poncho)      | 11434 | 0.0.0.0           | Needs Tailscale access from Bjorn |
| SearXNG              | 8888  | 127.0.0.1         | Local search only |
| Herald Orchestrator  | 8000  | 127.0.0.1         | Local orchestration |
| LM Studio            | 1234  | 127.0.0.1         | Set in LM Studio Server settings |
| TTS Server           | 8787  | 127.0.0.1         | Managed by daemon.py |

### Network ACL Middleware

`NetworkACLMiddleware` in `main.py` provides defense-in-depth: even if Moose
is accidentally bound to a LAN interface, only requests from `127.0.0.1`,
`::1`, and the Tailscale CGNAT range (`100.64.0.0/10`) are accepted.
Everything else receives `403 Forbidden`.

### WebSocket Origin Validation

The `/ws` endpoint validates both:
- **Source IP**: Must be localhost or Tailscale range (checked before `accept()`)
- **Origin header**: Must be in `profile.yaml` CORS list or from a Tailscale IP

### OpenAI-Compatible Endpoints (`/v1/`)

The `/v1/chat/completions` and `/v1/models` endpoints support authentication
via both:
- `Authorization: Bearer <key>` (OpenAI standard)
- `X-API-Key: <key>` (Moose standard)

Set `MOOSE_OPENAI_API_KEY` to use a separate key for external consumers.
Falls back to `MOOSE_API_KEY`.

### CDP (Chrome DevTools Protocol) Hardening

When OpenClaw launches Chromium, the CDP debug port **must** bind to
`127.0.0.1` only. When deploying OpenClaw, ensure:

```
--remote-debugging-address=127.0.0.1
--remote-debugging-port=9222
```

The `security_check.py` script will flag any CDP port not on loopback.

### Running the Security Check

```bash
# Normal check — fails on violations, warns on suspicious bindings
python3 security_check.py

# Strict mode — treats warnings as failures
python3 security_check.py --strict

# Machine-readable output
python3 security_check.py --json
```

The check runs automatically at startup (via `start.sh` and `daemon.py`).
In daemon mode, a FAIL result prevents the server from starting.

Results are logged to `~/Library/Logs/moose/security_check.log`.

### Ollama IPv6 Fix (Bjorn)

Ollama binds to `*:11434` on IPv6 by default, even when `OLLAMA_HOST` is set
for IPv4 only. To fix:

```bash
# Option 1: Environment variable (add to shell profile)
export OLLAMA_HOST=127.0.0.1:11434

# Option 2: launchd override (create ~/Library/LaunchAgents/local.ollama.env.plist)
# Set the OLLAMA_HOST env var before Ollama starts
```

### LM Studio Binding

LM Studio defaults to `0.0.0.0:1234`. Change this in:
**LM Studio → Server → Network → Listen address → `127.0.0.1`**

### Recommended UniFi Firewall Rules

Apply these on the VLAN where Bjorn and Poncho reside:

| Rule | Action | Source | Destination | Port | Protocol |
|------|--------|--------|-------------|------|----------|
| 1 | Allow | Tailscale subnet (100.64.0.0/10) | Bjorn LAN IP | 8000 | TCP |
| 2 | Allow | Poncho Tailscale IP | Bjorn Tailscale IP | 11434 | TCP |
| 3 | Drop | Any | Bjorn LAN IP | 1234 | TCP |
| 4 | Drop | Any | Bjorn LAN IP | 11434 | TCP |
| 5 | Drop | Any | Bjorn LAN IP | 9222 | TCP |
| 6 | Drop | Any | Bjorn LAN IP | 8787 | TCP |
| 7 | Drop | Any | Bjorn LAN IP | 8888 | TCP |

**IDS/IPS**: Enable "Emerging Threats" and "ET Open" rulesets. The CDP port
(9222) should trigger alerts if traffic is seen from non-loopback sources.

### Tailscale Mesh Topology

```
Bjorn (Mac Studio)     ── 100.126.201.109
  └─ Moose API :8000
  └─ LM Studio :1234 (local)
  └─ Ollama :11434 (local)

Poncho (Linux)         ── 100.107.61.25
  └─ Ollama :11434 (Tailscale-accessible)
  └─ OpenClaw (planned)
  └─ SearXNG (planned)
```

## Threat Model

### Assets Protected

1. **API Keys**: Authentication credentials
2. **User Data**: Conversations, tasks, memory
3. **System Access**: Shell commands, file system
4. **External Services**: LLM APIs, email sending

### In-Scope Threats

| Threat | Mitigation |
|--------|------------|
| Prompt Injection | Input sanitization, passive security monitoring |
| Path Traversal | Path resolution, symlink detection, blocklists |
| SQL Injection | Parameterized queries, allowlist keywords |
| Command Injection | Command allowlist, operator blocking |
| XSS | DOMPurify, CSP headers |
| CSRF | API key authentication, origin validation |
| SSRF | Private IP blocking, scheme validation |
| Email Header Injection | Header sanitization (CR/LF/null stripping) |

### Trust Boundaries

```
[User Browser]
     |
     | (Untrusted)
     v
[Frontend SPA]
     |
     | (API Key + Origin Check)
     v
[Backend API]
     |
     | (Internal, Semi-trusted)
     v
[LLM Inference]
     |
     | (Internal, Trusted)
     v
[SQLite Database]
```

### Agent Security

- **Tool Filtering**: Agents have access only to their allowed tool set
- **Security Agent**: Monitors all message bus traffic for suspicious patterns
- **Passive Security Check**: User input screened for known attack patterns
- **Escalation Flow**: Sensitive actions require explicit user approval

## Rust Migration Roadmap

The following security-critical components are candidates for Rust migration to improve memory safety and performance:

| Component | Status | Priority |
|-----------|--------|----------|
| Vector Memory | Planned | High |
| Input Sanitization | Planned | High |
| Path Validation | Planned | High |
| Audit Logger | Planned | Medium |
| SQL Query Validator | Planned | Medium |
| API Key Crypto | Planned | Medium |

Rust modules will expose Python bindings via PyO3.

## Security Testing

The test suite includes security-focused tests:

- `test_path_validation.py`: Path traversal, symlink attacks
- `test_sql_blocking.py`: SQL injection prevention
- `test_shell_commands.py`: Command injection prevention
- `test_websocket_auth.py`: WebSocket authentication
- `test_rate_limiting.py`: Rate limit enforcement
- `test_script_sandbox.py`: Script sandboxing
- `test_applescript_escaping.py`: AppleScript injection

Run security tests:
```bash
pytest backend/tests/ -v -k "security or sql or shell or path or rate"
```

## Dependency Security

- **Python**: `pip-audit` runs in CI to detect vulnerable dependencies
- **Node.js**: `npm audit` runs in CI for frontend dependencies
- **Rust**: `cargo-audit` configured for future Rust components

## Configuration Security

Sensitive configuration should use environment variables or `.secrets` files:

- `MOOSE_API_KEY`: Override auto-generated API key
- SMTP credentials: Store in environment, not profile.yaml
- Database path: Ensure proper permissions

Files excluded from version control (`.gitignore`):
- `.moose_api_key`
- `.env*`
- `*.db`
- `credentials.json`
- TLS certificates
