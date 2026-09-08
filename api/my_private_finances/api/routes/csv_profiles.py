from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from my_private_finances.deps import SessionDep
from my_private_finances.models import CsvProfile
from my_private_finances.schemas import (
    CsvProfileCreate,
    CsvProfileRead,
    CsvProfileUpdate,
)

router = APIRouter(prefix="/csv-profiles", tags=["csv-profiles"])

logger = logging.getLogger(__name__)


def _to_read(profile: CsvProfile) -> CsvProfileRead:
    assert profile.id is not None
    return CsvProfileRead(
        id=profile.id,
        name=profile.name,
        delimiter=profile.delimiter,
        date_format=profile.date_format,
        decimal_comma=profile.decimal_comma,
        column_map=profile.column_map,
    )


@router.get("", response_model=list[CsvProfileRead])
async def list_csv_profiles(session: SessionDep) -> list[CsvProfileRead]:
    profiles = (
        (await session.execute(select(CsvProfile).order_by(CsvProfile.name)))
        .scalars()
        .all()
    )
    return [_to_read(p) for p in profiles]


@router.post("", response_model=CsvProfileRead, status_code=201)
async def create_csv_profile(
    payload: Annotated[CsvProfileCreate, Body()],
    session: SessionDep,
) -> CsvProfileRead:
    db_obj = CsvProfile(
        name=payload.name,
        delimiter=payload.delimiter,
        date_format=payload.date_format,
        decimal_comma=payload.decimal_comma,
        column_map=payload.column_map,
    )
    session.add(db_obj)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="A profile with this name already exists"
        ) from e
    await session.refresh(db_obj)
    logger.info("CSV profile created: id=%d, name=%r", db_obj.id, db_obj.name)
    return _to_read(db_obj)


@router.get("/{profile_id}", response_model=CsvProfileRead)
async def get_csv_profile(profile_id: int, session: SessionDep) -> CsvProfileRead:
    db_obj = await session.get(CsvProfile, profile_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _to_read(db_obj)


@router.put("/{profile_id}", response_model=CsvProfileRead)
async def update_csv_profile(
    profile_id: int,
    payload: Annotated[CsvProfileUpdate, Body()],
    session: SessionDep,
) -> CsvProfileRead:
    db_obj = await session.get(CsvProfile, profile_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    if payload.name is not None:
        db_obj.name = payload.name
    if payload.delimiter is not None:
        db_obj.delimiter = payload.delimiter
    if payload.date_format is not None:
        db_obj.date_format = payload.date_format
    if payload.decimal_comma is not None:
        db_obj.decimal_comma = payload.decimal_comma
    if payload.column_map is not None:
        db_obj.column_map = payload.column_map

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="A profile with this name already exists"
        ) from e

    await session.refresh(db_obj)
    logger.info("CSV profile updated: id=%d, name=%r", db_obj.id, db_obj.name)
    return _to_read(db_obj)


@router.delete("/{profile_id}", status_code=204)
async def delete_csv_profile(profile_id: int, session: SessionDep) -> None:
    db_obj = await session.get(CsvProfile, profile_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    await session.delete(db_obj)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Profile is in use by a watch-folder config and cannot be deleted",
        ) from e
    logger.info("CSV profile deleted: id=%d", profile_id)
