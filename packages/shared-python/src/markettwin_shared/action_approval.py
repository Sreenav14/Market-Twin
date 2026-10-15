"""User-declared synthetic effects; page text alone never grants eligibility."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SensitiveActionRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    category: Literal["form_submit", "save", "create", "update", "publish"]
    role: Literal["button", "link", "menuitem"] = "button"
    name: str = Field(min_length=1, max_length=160)
    scope_role: Literal["form", "dialog", "region", "navigation", "listitem"] | None = None
    scope_name: str | None = Field(default=None, min_length=1, max_length=160)
    resource_reference: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    test_data_reset_confirmed: Literal[True]

    @model_validator(mode="after")
    def scope_is_exact(self) -> "SensitiveActionRule":
        if (self.scope_role is None) != (self.scope_name is None):
            raise ValueError("Approval scopes need both role and name.")
        return self

    def matches(self, action: dict[str, object]) -> bool:
        return all(action.get(key) == value for key, value in {
            "category": self.category, "role": self.role, "name": self.name,
            "scope_role": self.scope_role, "scope_name": self.scope_name,
        }.items())
