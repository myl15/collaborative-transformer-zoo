from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, Relationship


class User(SQLModel, table=True):
    """User account for authentication and ownership tracking."""
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    visualizations: list["Visualization"] = Relationship(back_populates="user")
    annotations: list["Annotation"] = Relationship(back_populates="user")


class Visualization(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    model_name: str
    input_text: str
    view_type: str
    html_content: str  # We store the huge HTML string here
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Foreign key to user (optional for now, for backwards compatibility)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    user: Optional[User] = Relationship(back_populates="visualizations")


class Annotation(SQLModel, table=True):
    """Comments/annotations on visualization attention tokens."""
    id: Optional[int] = Field(default=None, primary_key=True)
    viz_id: int = Field(foreign_key="visualization.id")
    user_id: int = Field(foreign_key="user.id")
    content: str
    start_token: int  # Index of start token
    end_token: int  # Index of end token
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: User = Relationship(back_populates="annotations")