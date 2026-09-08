from __future__ import annotations

from typing import Optional

from sqlmodel import Field, SQLModel


class WatchSettings(SQLModel, table=True):
    __tablename__ = "watch_settings"

    id: Optional[int] = Field(default=None, primary_key=True)
    root_path: str = Field(default="data/watch")


class WatchFolderConfig(SQLModel, table=True):
    __tablename__ = "watch_folder_config"

    id: Optional[int] = Field(default=None, primary_key=True)
    subfolder_name: str = Field(unique=True)
    account_id: int = Field(foreign_key="account.id", ondelete="CASCADE")
    profile_id: Optional[int] = Field(
        default=None, foreign_key="csv_profile.id", ondelete="SET NULL"
    )
