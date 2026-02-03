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
