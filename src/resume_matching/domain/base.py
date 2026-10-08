"""Base model for domain value objects that are persisted as JSON and exposed via the API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class DomainModel(BaseModel):
    """Pydantic model serialised with camelCase keys, accepting snake_case on input."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=False,
        extra="ignore",
    )

    def to_json_dict(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)
