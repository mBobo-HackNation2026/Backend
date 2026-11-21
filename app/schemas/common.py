from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    app_name: str
    environment: str
    version: str


class ErrorResponse(BaseModel):
    error_code: str
    message: str
