from pydantic import BaseModel, Field

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)

class LoginRequest(RegisterRequest):
    pass

class PhoneRequest(BaseModel):
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")

class CodeRequest(BaseModel):
    login_id: str
    code: str = Field(min_length=3, max_length=16)
    password: str | None = Field(default=None, max_length=128)

class LinksRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100000)

class SettingsRequest(BaseModel):
    delay_seconds: int = Field(ge=2, le=3600)
    rest_minutes: int = Field(ge=0, le=1440)

class ChargeRequest(BaseModel):
    user_id: int
    amount: int = Field(ge=1, le=1_000_000)
