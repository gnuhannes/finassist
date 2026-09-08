from typing import Any, cast

from pydantic import ConfigDict
from sqlmodel import SQLModel


class StrictSchema(SQLModel):
    model_config = cast(Any, ConfigDict(extra="forbid"))
