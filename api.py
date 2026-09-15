from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from git_analyzer import analyze_change
from repository_loader import RepositoryLoadError, is_github_url, open_repository


app = FastAPI(title="ImpactLens API")


class AnalyzeRequest(BaseModel):
    repository: str = Field(min_length=1)
    base_commit: str = Field(min_length=1)
    target_commit: str = Field(min_length=1)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze_repository_change(request: AnalyzeRequest):
    if not is_github_url(request.repository):
        raise HTTPException(
            status_code=400,
            detail="repository must be a public HTTPS GitHub URL",
        )

    try:
        with open_repository(
            request.repository,
            request.base_commit,
            request.target_commit,
        ) as repository:
            return analyze_change(
                repository,
                request.base_commit,
                request.target_commit,
            )
    except RepositoryLoadError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
