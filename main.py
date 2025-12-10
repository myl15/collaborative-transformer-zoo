from dotenv import load_dotenv
# Load environment variables from .env file.
load_dotenv()

from fastapi import FastAPI, Form, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from sqlmodel import Session, select
from sqlalchemy import func
import time
import json
import csv
import io
import zipfile
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Optional
import logging
from visualization_logic import get_viz_data, free_memory
from database import create_db_and_tables, get_session
from models import Visualization, User, Annotation, AuditLog
from auth import (
    hash_password, 
    verify_password, 
    create_access_token,
    get_current_user,
    get_current_user_optional,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from annotations import router as annotations_router
from validation import VisualizationRequest, validate_and_sanitize
from caching import cache_viz_result, get_cache_stats, clear_cache
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables() 
    yield

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: HTMLResponse(
    f"<h1>429 Too Many Requests</h1><p>{exc.detail}</p>",
    status_code=429
))

# 1. Mount Static Files (CSS/JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 2. Setup Jinja2 Templates
templates = Jinja2Templates(directory="templates")
app.include_router(annotations_router)


# === CACHING WRAPPER === #
@cache_viz_result(ttl_seconds=3600)
def get_cached_viz_data(model_name: str, text: str, view_type: str) -> str:
    return get_viz_data(model_name, text, view_type)


# === ROUTES === #
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/unload")
async def unload_and_go_home():
    free_memory()
    return RedirectResponse(url="/")

@app.get("/cache/stats")
async def cache_statistics():
    return get_cache_stats()

@app.get("/metrics")
async def metrics(session: Session = Depends(get_session)):
    metrics = getattr(app.state, "metrics", None) or {}
    times = metrics.get("viz_generation_time_seconds", [])
    avg_time = sum(times) / len(times) if times else 0.0
    total_viz = metrics.get("viz_generation_count", 0)
    model_load_failures = metrics.get("model_load_failures", 0)
    total_users = session.exec(select(func.count()).select_from(User)).one()

    result = {
        "viz_generation_count": total_viz,
        "avg_viz_generation_time_seconds": avg_time,
        "viz_generation_time_samples": len(times),
        "model_load_failures": model_load_failures,
        "total_users": total_users,
        "cache": get_cache_stats(),
    }
    return result

@app.post("/cache/clear")
async def clear_cache_endpoint():
    success = clear_cache()
    return {"success": success, "message": "Cache cleared" if success else "Failed to clear cache"}

@app.get("/visualizations", response_class=HTMLResponse)
async def list_visualizations(
    request: Request,
    model: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """
    List visualizations with optional filtering and pagination.
    1. Filter by model name
    2. Filter by search text in input_text
    3. Filter by date range
    4. Pagination
    """

    stmt = select(Visualization)
    if model:
        stmt = stmt.where(Visualization.model_name == model)
    if search:
        stmt = stmt.where(Visualization.input_text.ilike(f"%{search}%"))
    if date_from:
        try:
            dt = func.to_timestamp(date_from)
            if dt is not None:
                stmt = stmt.where(Visualization.created_at >= date_from)
        except Exception:
            pass

    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    stmt = stmt.order_by(Visualization.id.desc()).offset((page - 1) * limit).limit(limit)
    visualizations = session.exec(stmt).all()
    
    return templates.TemplateResponse("visualizations.html", {
        "request": request, 
        "visualizations": visualizations, 
        "page": page, 
        "limit": limit, 
        "total": total
    })

@app.post("/visualize")
@limiter.limit("5/minute")
async def create_visualization(
    request: Request,
    model_name: str = Form(...), 
    text: str = Form(...), 
    view_type: str = Form("head"),
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """ 
    Create a new visualization.
    """

    start = time.perf_counter()
    try:
        viz_request = validate_and_sanitize(model_name, text, view_type)
        
        html_content = get_cached_viz_data(
            viz_request.model_name, 
            viz_request.text, 
            viz_request.view_type
        )
        
        viz = Visualization(
            model_name=viz_request.model_name,
            input_text=viz_request.text,
            view_type=viz_request.view_type,
            html_content=html_content,
            is_public=(False if current_user else True),
            user_id=(current_user.id if current_user else None),
        )
        session.add(viz)
        session.commit()
        session.refresh(viz)
        
        duration = time.perf_counter() - start
        
        # Simple metrics
        app.state.metrics = getattr(app.state, "metrics", {
            "viz_generation_count": 0, "viz_generation_time_seconds": [], "model_load_failures": 0
        })
        app.state.metrics["viz_generation_count"] += 1
        app.state.metrics["viz_generation_time_seconds"].append(duration)

        logger.info(json.dumps({"event": "visualization_created", "viz_id": viz.id, "model": viz_request.model_name}))
        return RedirectResponse(url=f"/viz/{viz.id}", status_code=303)
        
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Visualization error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate visualization")

@app.get("/viz/{viz_id}/content", response_class=HTMLResponse)
async def get_visualization_content(viz_id: int, session: Session = Depends(get_session)):
    """
    Return the HTML content of a visualization with injected JS/CSS for annotations.
    """

    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")
    
    # Inject styling for the IFRAME content only
    raw_html = viz.html_content
    centering_style = """
    <style>
        body { position: relative; display: flex; justify-content: center; margin: 0; padding-top: 20px; width: 100%; min-height: 100vh; }
        #bertviz { margin: auto; }
        
        /* Pin Style */
        .viz-pin {
            position: absolute;
            width: 12px; height: 12px;
            background-color: #dc2626;
            border: 2px solid white;
            border-radius: 50%;
            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
            cursor: pointer;
            z-index: 1000;
            transform: translate(-50%, -50%); /* Center on the coordinate */
            transition: transform 0.2s;
        }
        .viz-pin:hover { transform: translate(-50%, -50%) scale(1.5); }
        
        /* Tooltip Style */
        .pin-tooltip {
            visibility: hidden;
            position: absolute;
            bottom: 150%;
            left: 50%;
            transform: translateX(-50%);
            background-color: #1e293b;
            color: #fff;
            text-align: center;
            padding: 5px 10px;
            border-radius: 6px;
            font-size: 12px;
            white-space: nowrap;
            z-index: 1001;
            opacity: 0;
            transition: opacity 0.3s;
        }
        .pin-tooltip::after {
            content: "";
            position: absolute;
            top: 100%; left: 50%;
            margin-left: -5px;
            border-width: 5px;
            border-style: solid;
            border-color: #1e293b transparent transparent transparent;
        }
        .viz-pin:hover .pin-tooltip { visibility: visible; opacity: 1; }
    </style>
    """

    # JS for Context-Aware Pins
    injection_script = f"""
    <script>
        const VIZ_ID = {viz_id};
        let currentAttentionType = "All"; // Default

        document.addEventListener("DOMContentLoaded", async function() {{
            const vizContainer = document.getElementById('bertviz') || document.body;
            vizContainer.style.position = 'relative';

            // --- A. DETECT BERTVIZ DROPDOWN ---
            // BertViz usually puts a <select> at the top for Encoder/Decoder switching.
            // We look for it and listen for changes.
            const selects = document.querySelectorAll("select");
            let viewSelect = null;
            
            // Heuristic: The attention selector usually has options like "Encoder", "Decoder"
            selects.forEach(s => {{
                if (s.innerHTML.includes("Encoder") || s.innerHTML.includes("Cross")) {{
                    viewSelect = s;
                }}
            }});

            if (viewSelect) {{
                // Set initial value
                currentAttentionType = viewSelect.value;
                console.log("Detected View Context:", currentAttentionType);

                // Listen for changes
                // Note: BertViz uses jQuery, so standard 'change' events might be intercepted, 
                // but usually bubbling works or we can poll.
                viewSelect.addEventListener("change", function(e) {{
                    currentAttentionType = e.target.value;
                    updatePinVisibility();
                }});
            }}

            // --- B. FETCH PINS ---
            try {{
                const res = await fetch(`/viz/${{VIZ_ID}}/annotations`);
                if (res.ok) {{
                    const annotations = await res.json();
                    annotations.forEach(ann => {{
                        if (ann.x_pos != null && ann.y_pos != null) {{
                            createPin(ann);
                        }}
                    }});
                    updatePinVisibility(); // Initial filter
                }}
            }} catch (err) {{ console.error(err); }}

            // --- C. RIGHT CLICK ---
            vizContainer.addEventListener("contextmenu", function(e) {{
                e.preventDefault();
                e.stopPropagation(); 
                
                const rect = vizContainer.getBoundingClientRect();
                const xPercent = ((e.clientX - rect.left) / rect.width) * 100;
                const yPercent = ((e.clientY - rect.top) / rect.height) * 100;

                // Draw temp pin ONLY if it matches current view
                drawTempPin(xPercent, yPercent);

                window.parent.postMessage({{
                    type: 'COORD_CLICK',
                    x: xPercent,
                    y: yPercent,
                    attention_type: currentAttentionType // SEND CONTEXT
                }}, "*");
            }});

            // --- D. HELPER FUNCTIONS ---
            
            function createPin(ann) {{
                const pin = document.createElement('div');
                pin.className = 'viz-pin';
                pin.style.left = ann.x_pos + '%';
                pin.style.top = ann.y_pos + '%';
                
                // Store context on the element itself
                pin.dataset.context = ann.attention_type || "All"; 
                
                const tooltip = document.createElement('span');
                tooltip.className = 'pin-tooltip';
                tooltip.innerHTML = `<strong>${{ann.username}}</strong>: ${{ann.content}}`;
                
                pin.appendChild(tooltip);
                vizContainer.appendChild(pin);
            }}

            function updatePinVisibility() {{
                const pins = document.querySelectorAll('.viz-pin');
                pins.forEach(p => {{
                    // Show if:
                    // 1. Pin is "All" (global)
                    // 2. Pin matches current context
                    // 3. Pin is the "Temp" pin (always show)
                    if (p.id === 'temp-viz-pin') return;

                    const pinContext = p.dataset.context;
                    if (pinContext === "All" || pinContext === currentAttentionType) {{
                        p.style.display = 'block';
                    }} else {{
                        p.style.display = 'none';
                    }}
                }});
            }}

            function drawTempPin(x, y) {{
                const existing = document.getElementById('temp-viz-pin');
                if (existing) existing.remove();

                const pin = document.createElement('div');
                pin.id = 'temp-viz-pin';
                pin.className = 'viz-pin';
                pin.style.left = x + '%';
                pin.style.top = y + '%';
                pin.style.backgroundColor = '#2563eb';
                pin.style.zIndex = '2000';
                vizContainer.appendChild(pin);
            }}
        }});
    </script>
    """

    # Inject
    modified_html = raw_html
    if "</head>" in modified_html:
        modified_html = modified_html.replace("</head>", f"{centering_style}{injection_script}</head>")
    else:
        modified_html = centering_style + injection_script + modified_html
        
    return modified_html

@app.get("/viz/{viz_id}", response_class=HTMLResponse)
async def get_visualization(
    viz_id: int,
    request: Request,
    share_token: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
):
    """
    Render the visualization page with annotations support.
    """

    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")

    is_owner = current_user is not None and viz.user_id == current_user.id
    if not viz.is_public and not is_owner:
        if not share_token or share_token != viz.share_token:
            raise HTTPException(status_code=403, detail="This visualization is private")

    # Log audit
    audit = AuditLog(viz_id=viz.id, user_id=(current_user.id if current_user else None), action="view", ip_address=request.client.host if request.client else None)
    session.add(audit)
    session.commit()

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


@app.get("/viz/{viz_id}/export")
async def export_visualization(viz_id: int, 
                               session: Session = Depends(get_session), 
                               current_user: Optional[User] = Depends(get_current_user_optional)):
    """
    Export visualization metadata + annotations as JSON.
    """

    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")

    # Only owner or public or share_token (not supported here) can export
    if not viz.is_public and (current_user is None or current_user.id != viz.user_id):
        raise HTTPException(status_code=403, detail="Not allowed to export this visualization")

    # Gather annotations
    stmt = select(Annotation).where(Annotation.viz_id == viz.id)
    annotations = session.exec(stmt).all()

    payload = {
        "id": viz.id,
        "model_name": viz.model_name,
        "input_text": viz.input_text,
        "view_type": viz.view_type,
        "created_at": viz.created_at.isoformat(),
        "annotations": [a.__dict__ for a in annotations],
    }

    # Audit
    audit = AuditLog(viz_id=viz.id, user_id=(current_user.id if current_user else None), action="export")
    session.add(audit)
    session.commit()

    logger.info(json.dumps({"event": "viz_export", "viz_id": viz.id, "user_id": (current_user.id if current_user else None)}))

    return payload


def _serialize_annotation(a: Annotation) -> dict:
    return {
        "id": a.id,
        "viz_id": a.viz_id,
        "user_id": a.user_id,
        "content": a.content,
        "start_token": a.start_token,
        "end_token": a.end_token,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


@app.get("/viz/{viz_id}/export.csv")
async def export_visualization_csv(viz_id: int, session: Session = Depends(get_session), current_user: Optional[User] = Depends(get_current_user_optional)):
    """
    Return a CSV representation of the visualization + annotations.
    """

    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")

    if not viz.is_public and (current_user is None or current_user.id != viz.user_id):
        raise HTTPException(status_code=403, detail="Not allowed to export this visualization")

    stmt = select(Annotation).where(Annotation.viz_id == viz.id)
    annotations = session.exec(stmt).all()

    output = io.StringIO()
    writer = csv.writer(output)
    # Write header for viz metadata
    writer.writerow(["viz_id", "model_name", "input_text", "view_type", "created_at"])
    writer.writerow([viz.id, viz.model_name, viz.input_text.replace('\n', ' '), viz.view_type, viz.created_at.isoformat()])
    writer.writerow([])
    # Annotations header
    writer.writerow(["annotation_id", "user_id", "content", "start_token", "end_token", "created_at", "updated_at"])
    for a in annotations:
        writer.writerow([a.id, a.user_id, a.content.replace('\n', ' '), a.start_token, a.end_token, a.created_at.isoformat() if a.created_at else None, a.updated_at.isoformat() if a.updated_at else None])

    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8")), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=viz_{viz.id}.csv"})


@app.get("/viz/{viz_id}/export.zip")
async def export_visualization_zip(viz_id: int, session: Session = Depends(get_session), current_user: Optional[User] = Depends(get_current_user_optional)):
    """
    Return a ZIP containing the HTML, JSON metadata, and CSV export.
    """

    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")

    if not viz.is_public and (current_user is None or current_user.id != viz.user_id):
        raise HTTPException(status_code=403, detail="Not allowed to export this visualization")

    # Prepare components
    stmt = select(Annotation).where(Annotation.viz_id == viz.id)
    annotations = session.exec(stmt).all()

    json_payload = {
        "id": viz.id,
        "model_name": viz.model_name,
        "input_text": viz.input_text,
        "view_type": viz.view_type,
        "created_at": viz.created_at.isoformat(),
        "annotations": [_serialize_annotation(a) for a in annotations],
    }

    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["annotation_id", "user_id", "content", "start_token", "end_token", "created_at", "updated_at"])
    for a in annotations:
        writer.writerow([a.id, a.user_id, a.content, a.start_token, a.end_token, a.created_at.isoformat() if a.created_at else None, a.updated_at.isoformat() if a.updated_at else None])

    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, mode="w") as zf:
        # HTML
        zf.writestr(f"viz_{viz.id}.html", viz.html_content)
        # JSON
        zf.writestr(f"viz_{viz.id}.json", json.dumps(json_payload, indent=2))
        # CSV
        zf.writestr(f"viz_{viz.id}_annotations.csv", csv_buffer.getvalue())

    zip_bytes.seek(0)
    return StreamingResponse(zip_bytes, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=viz_{viz.id}.zip"})


@app.post("/viz/{viz_id}/share")
async def generate_share_token(viz_id: int, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    """
    Owner-only: generate or reset a share_token and optionally make public.
    """

    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")
    if viz.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only owner can generate share tokens")

    token = secrets.token_urlsafe(16)
    viz.share_token = token
    viz.is_public = True
    session.add(viz)
    session.commit()
    session.refresh(viz)

    audit = AuditLog(viz_id=viz.id, user_id=current_user.id, action="share", details=f"token:{token}")
    session.add(audit)
    session.commit()

    return {"share_token": token, "is_public": viz.is_public}


@app.get("/user/{user_id}/export.csv")
async def export_user_csv(user_id: int, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    """
    Export all visualizations for a user as CSV (owner-only).
    """

    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    stmt = select(Visualization).where(Visualization.user_id == user_id)
    vizs = session.exec(stmt).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["viz_id", "model_name", "input_text", "view_type", "created_at", "is_public"])
    for v in vizs:
        writer.writerow([v.id, v.model_name, v.input_text.replace('\n', ' '), v.view_type, v.created_at.isoformat(), v.is_public])

    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8")), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=user_{user_id}_visualizations.csv"})


# ==== AUTH ENDPOINTS ==== #
@app.post("/auth/signup")
async def signup(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    """
    Register a new user.
    """

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
    """
    Login user and return JWT token.
    """
    
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