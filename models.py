from datetime import datetime
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship


class User(SQLModel, table=True):
    """
    User account for authentication and ownership tracking.
    Fields:
        - username: Unique username
        - email: Unique email address
        - hashed_password: Hashed password for authentication
        - created_at: Timestamp of account creation
    Relationships:
        - visualizations: Visualizations owned by the user
        - annotations: Annotations made by the user
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    visualizations: list["Visualization"] = Relationship(back_populates="user")
    annotations: list["Annotation"] = Relationship(back_populates="user")


class Visualization(SQLModel, table=True):
    """
    Visualization of model attention for a given input.
    Fields:
        - model_name: Name of the model
        - input_text: Text input visualized
        - view_type: Bertviz view type 
        - html_content: The HTML content of the visualization
        - is_public: Whether the viz is publicly accessible
        - share_token: Token for sharing private visualizations
        - created_at: Timestamp of creation
    Relationships:
        - user: Owner of the visualization
        - annotations: Annotations made on this visualization
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    model_name: str = Field(index=True)
    input_text: str = Field(index=False)
    view_type: str
    html_content: str  # We store the huge HTML string here
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    
    # Permissions / sharing
    is_public: bool = Field(default=False)
    share_token: Optional[str] = Field(default=None, index=True)

    # Foreign key to user
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    user: Optional[User] = Relationship(back_populates="visualizations")

    # Annotations relationship
    annotations: List["Annotation"] = Relationship(back_populates="visualization")


class Annotation(SQLModel, table=True):
    """
    Comments/annotations on visualization attention tokens.
    Fields:
        - viz_id: Foreign key to Visualization
        - user_id: Foreign key to User
        - content: Text of the annotation
        - start_token, end_token: Token range (optional)
        - x_pos, y_pos: Coordinates on the visualization (optional)
        - attention_type: Type of attention 
        - created_at, updated_at: Timestamps
    Relationships:
        - user: User who made the annotation
        - visualization: Visualization being annotated
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    viz_id: int = Field(foreign_key="visualization.id")
    user_id: int = Field(foreign_key="user.id")
    content: str
    
    # Make tokens optional
    start_token: Optional[int] = None
    end_token: Optional[int] = None
    
    # Add coordinate fields (using float for percentages, e.g., 50.5%)
    x_pos: Optional[float] = None
    y_pos: Optional[float] = None

    attention_type: Optional[str] = Field(default="All")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: User = Relationship(back_populates="annotations")
    visualization: "Visualization" = Relationship(back_populates="annotations")


class AuditLog(SQLModel, table=True):
    """
    Audit log for tracking user actions.
    Fields:
        - viz_id: Foreign key to Visualization
        - user_id: Foreign key to User
        - action: Description of the action
        - ip_address: IP address of the user
        - details: Additional details about the action
        - created_at: Timestamp of the action
    """
    
    id: Optional[int] = Field(default=None, primary_key=True)
    viz_id: Optional[int] = Field(default=None, foreign_key="visualization.id", index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    action: str  # e.g., 'view', 'export', 'share'
    ip_address: Optional[str] = None
    details: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)