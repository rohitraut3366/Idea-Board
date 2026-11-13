from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_serializer, field_validator


class IdeaCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    content: Annotated[str, Field(strict=True, min_length=1, max_length=2000)]

    @field_validator("content")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Content cannot contain NUL characters")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Content must be valid Unicode") from None
        return value


class IdeaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: AwareDatetime

    @field_serializer("id")
    def serialize_id(self, value: int) -> str:
        return str(value)
