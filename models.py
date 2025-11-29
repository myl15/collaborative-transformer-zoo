from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel

class Visualization(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    model_name: str
    input_text: str
    view_type: str
    html_content: str  # We store the huge HTML string here
    created_at: datetime = Field(default_factory=datetime.utcnow)