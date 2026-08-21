from typing import Literal, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class MeUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=80)
    username: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{3,32}$")
    fonnte_token: Optional[str] = Field(default=None, max_length=256)
    fonnte_from_number: Optional[str] = Field(default=None, max_length=32)
    current_password: Optional[str] = Field(default=None, max_length=128)
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=128)


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,32}$")
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "user"] = "user"
    display_name: str = Field(default="", max_length=80)
    fonnte_token: str = Field(default="", max_length=256)
    fonnte_from_number: str = Field(default="", max_length=32)


class UserUpdate(BaseModel):
    role: Optional[Literal["admin", "user"]] = None
    display_name: Optional[str] = Field(default=None, max_length=80)
    username: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{3,32}$")
    fonnte_token: Optional[str] = Field(default=None, max_length=256)
    fonnte_from_number: Optional[str] = Field(default=None, max_length=32)
    is_active: Optional[bool] = None
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=128)


class AssessRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    chat_history: str = Field(default="", max_length=8000)


class ReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: dict = Field(default_factory=dict)
    knowledge_chunks: str = Field(default="", max_length=8000)
    owner: Optional[str] = Field(default=None, max_length=64)


class MessageSend(BaseModel):
    to: str = Field(min_length=5, max_length=40)
    text: str = Field(min_length=1, max_length=4096)
    owner: Optional[str] = Field(default=None, max_length=64)


class ProductIn(BaseModel):
    id: Optional[str] = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="Umum", max_length=64)
    description: str = Field(default="", max_length=5000)
    price_range: str = Field(default="", max_length=100)
    duration: str = Field(default="", max_length=100)
    kb_text: str = Field(default="", max_length=50000)


class KnowledgeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    category: Optional[str] = Field(default=None, max_length=64)
    kb_text: Optional[str] = Field(default=None, max_length=50000)
