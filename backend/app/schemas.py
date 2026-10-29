from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)
    role: Literal["admin", "auditor", "officer"] = "officer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: str


class AccountCreate(BaseModel):
    id: str = Field(min_length=2, max_length=48, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=128)
    kind: Literal["department", "contractor", "beneficiary"] = "contractor"


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    kind: str
    flagged: bool


class TransactionCreate(BaseModel):
    sender: str
    receiver: str
    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    purpose: str = Field(default="", max_length=256)
    parent_token: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("receiver")
    @classmethod
    def _not_self(cls, v, info):
        if info.data.get("sender") == v:
            raise ValueError("sender and receiver must differ")
        return v


class TransactionOut(BaseModel):
    token: str
    parent_token: str | None
    sender: str
    receiver: str
    amount: float
    remaining: float
    purpose: str
    ts: int
    status: str
    risk_score: float
    risk_level: str
    risk_reasons: list[str]
    tx_hash: str
    batch_id: int | None


class AlertOut(BaseModel):
    id: int
    token: str
    level: str
    score: float
    reasons: list[str]
    status: str
    assignee: str | None
    note: str
    created_at: datetime


class AlertUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved", "dismissed"]
    note: str = Field(default="", max_length=2000)
    freeze: bool = False


class ScoreRequest(BaseModel):
    history: list[dict] = Field(min_length=1, max_length=50)
