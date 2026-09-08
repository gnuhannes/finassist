from __future__ import annotations

from fastapi import APIRouter

from my_private_finances.deps import SessionDep
from my_private_finances.schemas.ml import Suggestion, TrainResult
from my_private_finances.services.ml_categorization import suggest, train

router = APIRouter(prefix="/ml", tags=["ml"])


@router.post("/train", response_model=TrainResult)
async def train_model(session: SessionDep) -> TrainResult:
    return await train(session)


@router.get("/suggest", response_model=list[Suggestion])
async def get_suggestions(session: SessionDep) -> list[Suggestion]:
    return await suggest(session)
