"""Local REST API entry point."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("agents.pii_redaction.api:app", host="127.0.0.1", port=8000, reload=False)
