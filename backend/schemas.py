from typing import Any

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AdminBootstrapIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)
    setup_token: str


class ApiKeyIn(BaseModel):
    name: str = "default-key"
    permissions: str = "All"


class SettingsIn(BaseModel):
    default_model: str = "deepseek-chat"
    monthly_budget: float = Field(default=10.0, ge=0)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)
    language: str = "English"
    theme: str = "light"


class CreditTopUpIn(BaseModel):
    amount: float = Field(gt=0, le=10000)
    note: str = "manual top-up"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionIn(BaseModel):
    model: str = "deepseek-chat"
    messages: list[ChatMessage]
    stream: bool = False


class ProviderResult(BaseModel):
    content: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str = "stop"
    raw: dict[str, Any] = {}


class ProviderIn(BaseModel):
    name: str
    type: str = "openai_compatible"
    base_url: str
    status: str = "active"


class ProviderUpdateIn(BaseModel):
    name: str | None = None
    type: str | None = None
    base_url: str | None = None
    status: str | None = None


class ProviderCredentialIn(BaseModel):
    key_name: str
    api_key: str
    status: str = "active"


class ModelRouteIn(BaseModel):
    public_model: str
    provider_id: int
    provider_model: str
    input_price: float = Field(ge=0)
    output_price: float = Field(ge=0)
    priority: int = 100
    fallback_enabled: bool = True
    status: str = "active"


class ModelRouteUpdateIn(BaseModel):
    public_model: str | None = None
    provider_id: int | None = None
    provider_model: str | None = None
    input_price: float | None = Field(default=None, ge=0)
    output_price: float | None = Field(default=None, ge=0)
    priority: int | None = None
    fallback_enabled: bool | None = None
    status: str | None = None
