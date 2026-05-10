"""Entry point for running the SkillNexus API server."""

import uvicorn
from skillnexus.api import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("run_server:app", host="0.0.0.0", port=8000, reload=True)
