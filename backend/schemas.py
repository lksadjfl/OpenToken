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
    group_id: int | None = None
    quota: float = Field(default=0, ge=0)
    expires_at: str | None = None
    ip_whitelist: list[str] = Field(default_factory=list)
    ip_blacklist: list[str] = Field(default_factory=list)


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
    raw: dict[str, Any] = Field(default_factory=dict)


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


class AccountIn(BaseModel):
    name: str
    platform: str = "openai_compatible"
    type: str = "api_key"
    api_key: str = "mock"
    base_url: str = "mock://local"
    status: str = "active"
    schedulable: bool = True
    priority: int = 50
    concurrency: int = Field(default=3, ge=1)
    model_mapping: dict[str, str] = Field(default_factory=dict)


class AccountUpdateIn(BaseModel):
    name: str | None = None
    platform: str | None = None
    type: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    status: str | None = None
    schedulable: bool | None = None
    priority: int | None = None
    concurrency: int | None = Field(default=None, ge=1)
    model_mapping: dict[str, str] | None = None


class AccountCredentialIn(BaseModel):
    api_key: str


class ChannelIn(BaseModel):
    name: str
    status: str = "active"
    restrict_models: bool = False
    model_mapping: dict[str, str] = Field(default_factory=dict)
    model_pricing: list[dict[str, Any]] = Field(default_factory=list)
    billing_model_source: str = "requested"


class ChannelUpdateIn(BaseModel):
    name: str | None = None
    status: str | None = None
    restrict_models: bool | None = None
    model_mapping: dict[str, str] | None = None
    model_pricing: list[dict[str, Any]] | None = None
    billing_model_source: str | None = None


class GroupIn(BaseModel):
    name: str
    status: str = "active"
    rate_multiplier: float = Field(default=1.0, ge=0)
    rpm_limit: int = Field(default=60, ge=0)
    channel_ids: list[int] = Field(default_factory=list)
    fallback_group_id: int | None = None


class GroupUpdateIn(BaseModel):
    name: str | None = None
    status: str | None = None
    rate_multiplier: float | None = Field(default=None, ge=0)
    rpm_limit: int | None = Field(default=None, ge=0)
    channel_ids: list[int] | None = None
    fallback_group_id: int | None = None
