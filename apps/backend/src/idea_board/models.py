from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, MetaData, Text, func
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={"pk": "pk_%(table_name)s"})


class Idea(Base):
    __tablename__ = "ideas"
    __table_args__ = (
        CheckConstraint("char_length(content) BETWEEN 1 AND 2000", name="ck_ideas_content_length"),
        ExcludeConstraint(("content", "="), name="ex_ideas_content", using="hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
