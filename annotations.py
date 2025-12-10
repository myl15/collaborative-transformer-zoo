"""
Annotation CRUD endpoints for collaborative comments on visualizations.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlmodel import Session, select
from datetime import datetime
from typing import Optional

from database import get_session
from models import Annotation, User, Visualization
from auth import get_current_user

router = APIRouter(prefix="/viz", tags=["annotations"])


@router.get("/{viz_id}/annotations")
async def list_annotations(
    viz_id: int,
    session: Session = Depends(get_session),
):
    """List all annotations for a visualization."""
    # Verify viz exists
    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")
    
    statement = select(Annotation).where(Annotation.viz_id == viz_id)
    annotations = session.exec(statement).all()
    
    # Return as JSON with user info AND COORDINATES
    return [
        {
            "id": a.id,
            "viz_id": a.viz_id,
            "user_id": a.user_id,
            "username": a.user.username,
            "content": a.content,
            
            # Tokens
            "start_token": a.start_token,
            "end_token": a.end_token,
            
            # --- NEW: Return Coordinates ---
            "x_pos": a.x_pos,
            "y_pos": a.y_pos,

            "attention_type": a.attention_type,
            
            "created_at": a.created_at.isoformat(),
            "updated_at": a.updated_at.isoformat(),
        }
        for a in annotations
    ]


@router.post("/{viz_id}/annotations")
async def create_annotation(
    viz_id: int,
    content: str = Query(...),
    # Default tokens to None
    start_token: Optional[int] = Query(None),
    end_token: Optional[int] = Query(None),
    # Add coordinates
    x_pos: Optional[float] = Query(None),
    y_pos: Optional[float] = Query(None),
    authorization: Optional[str] = Header(None),
    attention_type: str = Query("All"),
    session: Session = Depends(get_session),
):
    """Create a new annotation on a visualization."""
    # Verify viz exists
    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")
    
    # Extract token from header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token"
        )
    token = authorization[7:]  # Remove "Bearer " prefix
    
    # Authenticate
    current_user = await get_current_user(token, session)
    
    # Validate token range
    if start_token is not None and end_token is not None:
        if start_token < 0 or end_token < start_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token range"
            )
    has_tokens = start_token is not None and end_token is not None
    has_coords = x_pos is not None and y_pos is not None

    if not has_tokens and not has_coords:
        raise HTTPException(status_code=400, detail="Must provide either token range or coordinates")
    
    # Create annotation
    annotation = Annotation(
        viz_id=viz_id,
        user_id=current_user.id,
        content=content,
        start_token=start_token,
        end_token=end_token,
        attention_type=attention_type,
        x_pos=x_pos,
        y_pos=y_pos
    )
    session.add(annotation)
    session.commit()
    session.refresh(annotation)
    
    return {
        "id": annotation.id,
        "viz_id": annotation.viz_id,
        "user_id": annotation.user_id,
        "username": current_user.username,
        "content": annotation.content,
        "start_token": annotation.start_token,
        "end_token": annotation.end_token,
        "created_at": annotation.created_at.isoformat(),
        "updated_at": annotation.updated_at.isoformat(),
    }


@router.patch("/annotations/{annotation_id}")
async def update_annotation(
    annotation_id: int,
    content: str = Query(...),
    authorization: Optional[str] = Header(None),
    session: Session = Depends(get_session),
):
    """Update an annotation (only owner can edit)."""
    annotation = session.get(Annotation, annotation_id)
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")
    
    # Extract token from header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token"
        )
    token = authorization[7:]  # Remove "Bearer " prefix
    
    # Authenticate
    current_user = await get_current_user(token, session)
    
    # Check ownership
    if annotation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own annotations"
        )
    
    annotation.content = content
    annotation.updated_at = datetime.utcnow()
    session.add(annotation)
    session.commit()
    session.refresh(annotation)
    
    return {
        "id": annotation.id,
        "viz_id": annotation.viz_id,
        "user_id": annotation.user_id,
        "username": annotation.user.username,
        "content": annotation.content,
        "start_token": annotation.start_token,
        "end_token": annotation.end_token,
        "created_at": annotation.created_at.isoformat(),
        "updated_at": annotation.updated_at.isoformat(),
    }


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(
    annotation_id: int,
    authorization: Optional[str] = Header(None),
    session: Session = Depends(get_session),
):
    """Delete an annotation (only owner can delete)."""
    annotation = session.get(Annotation, annotation_id)
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")
    
    # Extract token from header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token"
        )
    token = authorization[7:]  # Remove "Bearer " prefix
    
    # Authenticate
    current_user = await get_current_user(token, session)
    
    # Check ownership
    if annotation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own annotations"
        )
    
    session.delete(annotation)
    session.commit()
    
    return {"detail": "Annotation deleted"}
