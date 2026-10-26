import logging
import threading
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from git_analyzer import AnalysisGitError, AnalysisTimeoutError, analyze_change
from repository_loader import (
    RepositoryLoadError,
    RepositoryTimeoutError,
    is_github_url,
    normalize_github_url,
    open_repository,
)
from request_budget import RequestDeadlineExceeded, check_deadline, request_deadline


app = FastAPI(title="ImpactLens API")
logger = logging.getLogger(__name__)
MAX_CONCURRENT_ANALYSES = 2
MAX_REQUEST_SECONDS = 120
analysis_slots = threading.BoundedSemaphore(MAX_CONCURRENT_ANALYSES)


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


class ResolvedCommits(APIModel):
    base: str
    target: str | None


class SymbolLocation(APIModel):
    source: Literal["base", "target"]
    id: str
    path: str
    qualname: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


class CallSite(APIModel):
    source: Literal["base", "target"]
    caller_id: str
    callee_id: str
    path: str
    line: int = Field(ge=1)
    line_end: int = Field(ge=1)
    column: int = Field(ge=0)
    expression: str
    resolution: Literal["local", "import"]
    code: str
    code_truncated: bool


class AnalyzeResponse(ImpactSummary):
    schema_version: Literal[2]
    resolved_commits: ResolvedCommits
    symbol_locations: list[SymbolLocation]
    call_sites: list[CallSite]
    repository_url: str | None = None
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

    if not analysis_slots.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Analysis is busy. Try again shortly.")

    try:
        with request_deadline(MAX_REQUEST_SECONDS):
            with open_repository(
                request.repository,
                request.base_commit,
                request.target_commit,
            ) as repository:
                report = analyze_change(
                    repository,
                    request.base_commit,
                    request.target_commit,
                )
                report["repository_url"] = normalize_github_url(request.repository).removesuffix(".git")
            check_deadline()
            return report
    except (RepositoryTimeoutError, AnalysisTimeoutError, RequestDeadlineExceeded) as error:
        raise HTTPException(status_code=504, detail=str(error)) from error
    except AnalysisGitError as error:
        logger.error(
            "Git failed during analysis: operation=%s exit_code=%s stderr=%s",
            error.operation, error.returncode, error.diagnostic_stderr or "(empty)",
        )
        raise HTTPException(status_code=500, detail=str(error)) from error
    except RepositoryLoadError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        analysis_slots.release()
