from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from idea_board.database import DatabaseSession
from idea_board.models import Idea
from idea_board.schemas import IdeaCreate, IdeaResponse

router = APIRouter()


@router.get("/api/ideas")
def list_ideas(
    response: Response,
    session: DatabaseSession,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    before_id: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
) -> list[IdeaResponse]:
    if before_id is not None and limit is None:
        raise HTTPException(status_code=422, detail="before_id requires limit")

    query = select(Idea).order_by(Idea.id.desc())
    if before_id is not None:
        query = query.where(Idea.id < before_id)
    if limit is not None:
        query = query.limit(limit + 1)

    ideas = list(session.scalars(query))
    if limit is not None and len(ideas) > limit:
        ideas.pop()
        response.headers["Link"] = (
            f'</api/ideas?limit={limit}&before_id={ideas[-1].id}>; rel="next"'
        )
    return [IdeaResponse.model_validate(idea) for idea in ideas]


@router.post("/api/ideas", status_code=status.HTTP_201_CREATED)
def create_idea(payload: IdeaCreate, session: DatabaseSession) -> IdeaResponse:
    with session.begin():
        idea = session.scalar(
            insert(Idea)
            .values(content=payload.content)
            .on_conflict_do_nothing(constraint="ex_ideas_content")
            .returning(Idea)
        )
        if idea is None:
            raise HTTPException(status_code=409, detail="This idea is already on the board")
    return IdeaResponse.model_validate(idea)


@router.delete("/api/ideas/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_idea(
    idea_id: Annotated[int, Path(ge=1, le=2**63 - 1)], session: DatabaseSession
) -> Response:
    with session.begin():
        deleted_id = session.scalar(delete(Idea).where(Idea.id == idea_id).returning(Idea.id))
        if deleted_id is None:
            raise HTTPException(status_code=404, detail="Idea not found")
    return Response(status_code=204)


@router.get("/health")
def health(session: DatabaseSession) -> dict[str, str]:
    session.execute(select(Idea.id).limit(1))
    return {"status": "ok"}
