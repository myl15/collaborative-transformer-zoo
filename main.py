from fastapi import FastAPI, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from sqlmodel import Session, select
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Optional

# Import our new modules
from visualization_logic import get_viz_data, free_memory
from database import create_db_and_tables, get_session
from models import Visualization, User, Annotation
from auth import (
    hash_password, 
    verify_password, 
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from annotations import router as annotations_router


'''
    Uvicorn based FastAPI server for the Collaborative Transformer Zoo.
    - Home page with form to submit model name, input text, and view type.
    - Endpoint to create visualization, store in Postgres, and redirect.
    - Endpoint to retrieve visualization from Postgres by ID.
    - User authentication (signup/login) with JWT.
    - Annotation endpoints for collaborative comments.
'''

# Lifecycle: Run this when server starts
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables() # <--- Creates tables in Postgres
    yield

app = FastAPI(lifespan=lifespan)
# Serve static assets (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")
# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")
app.include_router(annotations_router)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/unload")
async def unload_and_go_home():
    free_memory()
    return RedirectResponse(url="/")


@app.get("/visualizations", response_class=HTMLResponse)
async def list_visualizations(request: Request, session: Session = Depends(get_session)):
    """List saved visualizations with links to their permanent pages."""
    statement = select(Visualization).order_by(Visualization.id.desc())
    visualizations = session.exec(statement).all()
    return templates.TemplateResponse("visualizations.html", {"request": request, "visualizations": visualizations})

# --- Write to DB and Redirect ---
@app.post("/visualize")
async def create_visualization(
    model_name: str = Form(...), 
    text: str = Form(...), 
    view_type: str = Form("head"),
    session: Session = Depends(get_session) # Inject DB session
):
    # 1. Generate the HTML (Expensive GPU operation)
    html_content = get_viz_data(model_name, text, view_type)
    
    # 2. Save to Postgres
    viz = Visualization(
        model_name=model_name,
        input_text=text,
        view_type=view_type,
        html_content=html_content
    )
    session.add(viz)
    session.commit()
    session.refresh(viz) # Get the new ID
    
    # 3. Redirect to the PERMANENT URL
    return RedirectResponse(url=f"/viz/{viz.id}", status_code=303)

# --- NEW: READ FROM DB ---
@app.get("/viz/{viz_id}", response_class=HTMLResponse)
async def get_visualization(viz_id: int, request: Request, session: Session = Depends(get_session)):
    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")

    other_view = "model" if viz.view_type == "head" else "head"
    other_label = "Switch to Model View" if viz.view_type == "head" else "Switch to Head View"

    stmt_prev = select(Visualization).where(Visualization.id < viz_id).order_by(Visualization.id.desc())
    prev_viz = session.exec(stmt_prev).first()
    stmt_next = select(Visualization).where(Visualization.id > viz_id).order_by(Visualization.id.asc())
    next_viz = session.exec(stmt_next).first()

    return templates.TemplateResponse("viz.html", {
        "request": request,
        "viz": viz,
        "other_view": other_view,
        "other_label": other_label,
        "prev_viz": prev_viz,
        "next_viz": next_viz
    })


# ===== AUTH ENDPOINTS =====
@app.post("/auth/signup")
async def signup(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    """Register a new user."""
    # Check if user exists
    statement = select(User).where(User.username == username)
    existing = session.exec(statement).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Check if email exists
    statement = select(User).where(User.email == email)
    existing = session.exec(statement).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )
    
    # Create user
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password)
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    
    # Create token
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id}


@app.post("/auth/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    """Login user and return JWT token."""
    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()
    
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id}