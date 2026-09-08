from typing import Optional
from pydantic import BaseModel


class Complaint(BaseModel):
    description: str
    category: str
    state: str
    location: str
    language: str = "en"
    status: str = "Pending"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_accuracy: Optional[float] = None
    location_captured_at: Optional[str] = None