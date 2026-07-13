# MarketTwin Control API

The FastAPI control plane for MarketTwin.

## Responsibilities

- MarketTwin user-token validation
- Workspace authorization
- Product Blueprint APIs
- Source Asset metadata
- Presigned object-storage upload URLs
- Knowledge review APIs
- Skill, Agent Blueprint and Mission Template APIs
- Application Target APIs
- Test Plan creation
- Test Run creation and cancellation
- Human Action Requests
- Interactive-browser access tokens
- Server-Sent Events
- Report retrieval
- Audit records
- Transactional outbox

## Excluded responsibilities

The Control API must not:

- Process videos
- Parse large documents
- Run Chromium
- Execute agents
- Generate final reports synchronously
