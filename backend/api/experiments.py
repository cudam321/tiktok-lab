"""Experiment tracking endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import ExperimentStatus
from services import experiments as exp_service

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


# --- Response Models ---


class ExperimentResponse(BaseModel):
    id: int
    name: str
    hypothesis: str | None
    variable: str
    variants: list[str]
    metric_target: str
    min_sample_size: int
    status: ExperimentStatus
    result_summary: str | None
    confidence: float | None
    account_id: int | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class CreateExperimentRequest(BaseModel):
    name: str
    variable: str
    variants: list[str]
    hypothesis: str | None = None
    metric_target: str = "engagement_rate"
    min_sample_size: int = 10
    account_id: int | None = None


class UpdateExperimentRequest(BaseModel):
    name: str | None = None
    hypothesis: str | None = None


class AssignVariantRequest(BaseModel):
    post_id: int
    variant_name: str


class AssignmentResponse(BaseModel):
    id: int
    post_id: int
    experiment_id: int
    variant_name: str

    model_config = {"from_attributes": True}


class VariableListResponse(BaseModel):
    variables: list[str]


# --- Routes ---


@router.get("/variables", response_model=VariableListResponse)
async def list_variables():
    return VariableListResponse(variables=exp_service.EXPERIMENT_VARIABLES)


@router.get("", response_model=list[ExperimentResponse])
async def list_experiments(
    status: ExperimentStatus | None = None,
    account_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    exps = await exp_service.list_experiments(db, status, account_id)
    return [ExperimentResponse.model_validate(e) for e in exps]


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(experiment_id: int, db: AsyncSession = Depends(get_db)):
    exp = await exp_service.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return ExperimentResponse.model_validate(exp)


@router.post("", response_model=ExperimentResponse, status_code=201)
async def create_experiment(
    body: CreateExperimentRequest, db: AsyncSession = Depends(get_db)
):
    try:
        exp = await exp_service.create_experiment(
            db,
            name=body.name,
            variable=body.variable,
            variants=body.variants,
            hypothesis=body.hypothesis,
            metric_target=body.metric_target,
            min_sample_size=body.min_sample_size,
            account_id=body.account_id,
        )
        return ExperimentResponse.model_validate(exp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{experiment_id}", response_model=ExperimentResponse)
async def update_experiment(
    experiment_id: int,
    body: UpdateExperimentRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        exp = await exp_service.update_experiment(
            db, experiment_id, name=body.name, hypothesis=body.hypothesis
        )
        return ExperimentResponse.model_validate(exp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{experiment_id}/start", response_model=ExperimentResponse)
async def start_experiment(experiment_id: int, db: AsyncSession = Depends(get_db)):
    try:
        exp = await exp_service.start_experiment(db, experiment_id)
        return ExperimentResponse.model_validate(exp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{experiment_id}/complete", response_model=ExperimentResponse)
async def complete_experiment(experiment_id: int, db: AsyncSession = Depends(get_db)):
    try:
        exp = await exp_service.complete_experiment(db, experiment_id)
        return ExperimentResponse.model_validate(exp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{experiment_id}")
async def delete_experiment(experiment_id: int, db: AsyncSession = Depends(get_db)):
    try:
        success = await exp_service.delete_experiment(db, experiment_id)
        if not success:
            raise HTTPException(status_code=404, detail="Experiment not found")
        return {"detail": "Experiment deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Variant Assignment ---


@router.post("/{experiment_id}/assign", response_model=AssignmentResponse)
async def assign_variant(
    experiment_id: int,
    body: AssignVariantRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        assignment = await exp_service.assign_post_to_variant(
            db, body.post_id, experiment_id, body.variant_name
        )
        return AssignmentResponse.model_validate(assignment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{experiment_id}/counts")
async def variant_counts(experiment_id: int, db: AsyncSession = Depends(get_db)):
    counts = await exp_service.get_variant_counts(db, experiment_id)
    return {"experiment_id": experiment_id, "counts": counts}


# --- Statistical Comparison ---


@router.get("/{experiment_id}/compare")
async def compare_experiment(experiment_id: int, db: AsyncSession = Depends(get_db)):
    try:
        result = await exp_service.compare_experiment(db, experiment_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
