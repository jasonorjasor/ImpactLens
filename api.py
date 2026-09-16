from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from git_analyzer import analyze_change
from repository_loader import RepositoryLoadError, is_github_url, open_repository


app = FastAPI(title="ImpactLens API")


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeRequest(BaseModel):
    repository: str = Field(min_length=1)
    base_commit: str = Field(min_length=1)
    target_commit: str = Field(min_length=1)


class ImpactPath(APIModel):
    source: Literal["base", "target"]
    symbols: list[str]


class ChangedSymbol(APIModel):
    id: str
    path: str
    qualname: str
    line_start: int
    line_end: int
    changed_lines: list[int]
    removed_lines: list[int] = Field(default_factory=list)
    change_type: Literal["added", "deleted", "renamed"] | None = None
    previous_id: str | None = None
    impact_paths: list[ImpactPath]


class AffectedRoute(APIModel):
    symbol_id: str
    method: str
    path: str


class ImpactSummary(APIModel):
    affected_symbols: list[str]
    affected_routes: list[AffectedRoute]
    related_tests: list[str]


class AnalysisError(APIModel):
    source: Literal["base", "target"]
    path: str
    error: str


class AnalyzeResponse(ImpactSummary):
    base_commit: str
    target_commit: str
    changed_symbols: list[ChangedSymbol]
    evidence_paths: list[ImpactPath]
    historical_impact: ImpactSummary
    analysis_errors: list[AnalysisError]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse, response_model_exclude_none=True)
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
