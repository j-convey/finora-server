from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    message: str
    version: str


class DatabaseHealthResponse(HealthResponse):
    database: str
