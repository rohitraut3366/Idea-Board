from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from idea_board.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    return create_engine(settings.database_url.get_secret_value())


def get_session(request: Request) -> Iterator[Session]:
    engine = cast(Engine, request.app.state.engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


DatabaseSession = Annotated[Session, Depends(get_session)]
