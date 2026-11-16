import os
from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session


def create_database_engine() -> Engine:
    return create_engine(os.environ["DATABASE_URL"])


def get_session(request: Request) -> Iterator[Session]:
    engine = cast(Engine, request.app.state.engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


DatabaseSession = Annotated[Session, Depends(get_session)]
