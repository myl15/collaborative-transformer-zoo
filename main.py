from fastapi import FastAPI, Form, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlmodel import Session, select
from sqlalchemy import func
import time
import json
import csv
import io
import zipfile
import secrets
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Optional
import logging

# Import our new modules
from visualization_logic import get_viz_data, free_memory
from database import create_db_and_tables, get_session
from models import Visualization, User, Annotation, AuditLog
from auth import (
    hash_password, 
    verify_password, 
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from auth import get_current_user_optional
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

STYLES = """
<style>
    body { font-family: sans-serif; background-color: #f4f4f9; margin: 0; display: flex; flex-direction: column; align-items: center; min-height: 100vh; }
    .container { background: white; padding: 2rem; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 90%; max-width: 1000px; margin-top: 2rem; }
    textarea { width: 100%; height: 100px; margin-bottom: 1rem; padding: 8px; }
    input[type="text"] { width: 100%; padding: 10px; margin-bottom: 1rem; }
    .btn { padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; margin-right: 10px; }
    .btn-primary { background: #007bff; color: white; }
    .btn-secondary { background: #6c757d; color: white; }
    .btn-outline { border: 1px solid #007bff; color: #007bff; background: white; }
    .controls { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 1px solid #eee; }
</style>
"""


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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: HTMLResponse(
    f"<h1>429 Too Many Requests</h1><p>{exc.detail}</p>",
    status_code=429
))
# Serve static assets (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")
# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")
app.include_router(annotations_router)


# === CACHING WRAPPER ===
@cache_viz_result(ttl_seconds=3600)
def get_cached_viz_data(model_name: str, text: str, view_type: str) -> str:
    """Wrapped GPU inference with Redis caching (1 hour TTL)."""
    return get_viz_data(model_name, text, view_type)


# === ROUTES ===
@app.get("/", response_class=HTMLResponse)
async def home():
    return f"""
    <html>
        <head><title>Transformer Zoo</title>{STYLES}
        <style>
            .auth-section {{ background: #f9f9f9; padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem; border-left: 4px solid #28a745; }}
            .auth-section h3 {{ margin-top: 0; color: #333; }}
            .auth-tabs {{ display: flex; gap: 1rem; margin-bottom: 1rem; }}
            .auth-tab {{ padding: 8px 16px; cursor: pointer; background: #e0e0e0; border: none; border-radius: 4px; font-weight: bold; }}
            .auth-tab.active {{ background: #007bff; color: white; }}
            .auth-form {{ display: none; }}
            .auth-form.active {{ display: block; }}
            .auth-form input {{ width: 100%; padding: 10px; margin-bottom: 1rem; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; }}
            .auth-form button {{ width: 100%; padding: 10px; margin-bottom: 0.5rem; }}
            .user-info {{ padding: 1rem; background: #d4edda; border-radius: 4px; color: #155724; display: none; }}
            .user-info.active {{ display: block; }}
        </style>
        </head>
        <body>
            <div class="container">
                <h1>Collaborative Transformer Zoo</h1>
                
                <!-- Auth Section -->
                <div class="auth-section">
                    <div class="user-info" id="user-info">
                        Logged in as: <strong id="username-display"></strong> 
                        <button class="btn btn-secondary" onclick="logout()" style="float: right;">Logout</button>
                    </div>
                    <div id="auth-forms">
                        <h3>Account</h3>
                        <div class="auth-tabs">
                            <button class="auth-tab active" onclick="switchTab('login')">Login</button>
                            <button class="auth-tab" onclick="switchTab('signup')">Sign Up</button>
                        </div>
                        
                        <!-- Login Form -->
                        <form class="auth-form active" id="login-form" onsubmit="handleLogin(event)">
                            <input type="text" placeholder="Username" id="login-username" required>
                            <input type="password" placeholder="Password" id="login-password" required>
                            <button type="submit" class="btn btn-primary">Login</button>
                            <p id="login-error" style="color: red; display: none;"></p>
                        </form>
                        
                        <!-- Signup Form -->
                        <form class="auth-form" id="signup-form" onsubmit="handleSignup(event)">
                            <input type="text" placeholder="Username" id="signup-username" required>
                            <input type="email" placeholder="Email" id="signup-email" required>
                            <input type="password" placeholder="Password" id="signup-password" required>
                            <button type="submit" class="btn btn-primary">Sign Up</button>
                            <p id="signup-error" style="color: red; display: none;"></p>
                        </form>
                    </div>
                </div>

                <!-- Visualization Form -->
                <form action="/visualize" method="post">
                    <label><strong>Model Name:</strong></label>
                    <input type="text" name="model_name" value="google/gemma-2b">
                    <label><strong>View Type:</strong></label>
                    <select name="view_type" style="margin-bottom: 1rem; padding: 5px;">
                        <option value="head">Head View (Lines)</option>
                        <option value="model">Model View (Blocks)</option>
                    </select>
                    <br><label><strong>Input Text:</strong></label>
                    <textarea name="text">The cat sat on the mat.</textarea>
                    <button type="submit" class="btn btn-primary">Visualize</button>
                </form>
            </div>

            <script>
                // Check if logged in on page load
                window.addEventListener('load', checkLoginStatus);

                function checkLoginStatus() {{
                    const token = localStorage.getItem('auth_token');
                    const username = localStorage.getItem('username');
                    if (token && username) {{
                        document.getElementById('auth-forms').style.display = 'none';
                        document.getElementById('user-info').classList.add('active');
                        document.getElementById('username-display').textContent = username;
                    }}
                }}

                function switchTab(tab) {{
                    document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
                    document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
                    
                    event.target.classList.add('active');
                    document.getElementById(tab + '-form').classList.add('active');
                }}

                async function handleLogin(event) {{
                    event.preventDefault();
                    const username = document.getElementById('login-username').value;
                    const password = document.getElementById('login-password').value;
                    const errorEl = document.getElementById('login-error');

                    try {{
                        const formData = new FormData();
                        formData.append('username', username);
                        formData.append('password', password);

                        const res = await fetch('/auth/login', {{
                            method: 'POST',
                            body: formData
                        }});

                        if (res.ok) {{
                            const data = await res.json();
                            localStorage.setItem('auth_token', data.access_token);
                            localStorage.setItem('username', username);
                            errorEl.style.display = 'none';
                            checkLoginStatus();
                            document.getElementById('login-username').value = '';
                            document.getElementById('login-password').value = '';
                        }} else {{
                            const error = await res.json();
                            errorEl.textContent = error.detail || 'Login failed';
                            errorEl.style.display = 'block';
                        }}
                    }} catch (err) {{
                        errorEl.textContent = 'Error: ' + err.message;
                        errorEl.style.display = 'block';
                    }}
                }}

                async function handleSignup(event) {{
                    event.preventDefault();
                    const username = document.getElementById('signup-username').value;
                    const email = document.getElementById('signup-email').value;
                    const password = document.getElementById('signup-password').value;
                    const errorEl = document.getElementById('signup-error');

                    try {{
                        const formData = new FormData();
                        formData.append('username', username);
                        formData.append('email', email);
                        formData.append('password', password);

                        const res = await fetch('/auth/signup', {{
                            method: 'POST',
                            body: formData
                        }});

                        if (res.ok) {{
                            const data = await res.json();
                            localStorage.setItem('auth_token', data.access_token);
                            localStorage.setItem('username', username);
                            errorEl.style.display = 'none';
                            checkLoginStatus();
                            document.getElementById('signup-username').value = '';
                            document.getElementById('signup-email').value = '';
                            document.getElementById('signup-password').value = '';
                        }} else {{
                            const error = await res.json();
                            errorEl.textContent = error.detail || 'Signup failed';
                            errorEl.style.display = 'block';
                        }}
                    }} catch (err) {{
                        errorEl.textContent = 'Error: ' + err.message;
                        errorEl.style.display = 'block';
                    }}
                }}

                function logout() {{
                    localStorage.removeItem('auth_token');
                    localStorage.removeItem('username');
                    document.getElementById('user-info').classList.remove('active');
                    document.getElementById('auth-forms').style.display = 'block';
                    location.reload();
                }}
            </script>
        </body>
    </html>
    """

@app.get("/unload")
async def unload_and_go_home():
    free_memory()
    return RedirectResponse(url="/")


@app.get("/cache/stats")
async def cache_statistics():
    """Get Redis cache statistics."""
    return get_cache_stats()


@app.get("/metrics")
async def metrics(session: Session = Depends(get_session)):
    """Return simple JSON metrics for observability."""
    metrics = getattr(app.state, "metrics", None) or {}
    # derive some summarized metrics
    times = metrics.get("viz_generation_time_seconds", [])
    avg_time = sum(times) / len(times) if times else 0.0
    total_viz = metrics.get("viz_generation_count", 0)
    model_load_failures = metrics.get("model_load_failures", 0)

    # active users = number of users in DB
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
    """Clear all cached visualizations."""
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
    """List saved visualizations with optional filtering and pagination."""
    stmt = select(Visualization)
    if model:
        stmt = stmt.where(Visualization.model_name == model)
    if search:
        # simple ILIKE-style search
        stmt = stmt.where(Visualization.input_text.ilike(f"%{search}%"))
    if date_from:
        try:
            dt = func.to_timestamp(date_from)
        except Exception:
            dt = None
        if dt is not None:
            stmt = stmt.where(Visualization.created_at >= date_from)
    # Order and paginate
    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    stmt = stmt.order_by(Visualization.id.desc()).offset((page - 1) * limit).limit(limit)
    visualizations = session.exec(stmt).all()
    return templates.TemplateResponse("visualizations.html", {"request": request, "visualizations": visualizations, "page": page, "limit": limit, "total": total})

# --- Write to DB and Redirect ---
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
    """Generate and store visualization with rate limiting and caching."""
    start = time.perf_counter()
    try:
        # Validate and sanitize inputs
        viz_request = validate_and_sanitize(model_name, text, view_type)
        
        # Get viz (cached if possible)
        html_content = get_cached_viz_data(
            viz_request.model_name, 
            viz_request.text, 
            viz_request.view_type
        )
        
        # Save to Postgres
        viz = Visualization(
            model_name=viz_request.model_name,
            input_text=viz_request.text,
            view_type=viz_request.view_type,
            html_content=html_content,
            # If a user is creating this, keep it private by default; anonymous submissions remain public
            is_public=(False if current_user else True),
            user_id=(current_user.id if current_user else None),
        )
        session.add(viz)
        session.commit()
        session.refresh(viz)
        duration = time.perf_counter() - start
        # Simple in-memory metrics (kept minimal for this project)
        app.state.metrics = getattr(app.state, "metrics", {
            "viz_generation_count": 0,
            "viz_generation_time_seconds": [],
            "model_load_failures": 0,
        })
        app.state.metrics["viz_generation_count"] += 1
        app.state.metrics["viz_generation_time_seconds"].append(duration)

        logger.info(json.dumps({"event": "visualization_created", "viz_id": viz.id, "model": viz_request.model_name, "duration": duration}))
        return RedirectResponse(url=f"/viz/{viz.id}", status_code=303)
        
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Visualization error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate visualization")

@app.get("/viz/{viz_id}/content", response_class=HTMLResponse)
async def get_visualization_content(viz_id: int, session: Session = Depends(get_session)):
    """Serves the raw HTML of a visualization with injected CSS for centering."""
    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")
    
    raw_html = viz.html_content

    # --- THE FIX: Inject CSS to center the content ---
    # We add Flexbox styling to the <body> of the iframe's internal HTML
    centering_style = """
    <style>
        body {
            display: flex;
            justify-content: center; /* Centers horizontally */
            align-items: flex-start; /* Keeps top alignment (better for scrolling) */
            margin: 0;
            padding-top: 20px;
            width: 100%;
        }
        /* Ensure the main visualization container doesn't overflow weirdly */
        #bertviz {
            margin: auto;
        }
    </style>
    """

    # We inject our style right before the closing </head> tag
    # This ensures it applies to the loaded content
    if "</head>" in raw_html:
        modified_html = raw_html.replace("</head>", f"{centering_style}</head>")
        return modified_html
    else:
        # Fallback if no head tag found (rare)
        return centering_style + raw_html


# --- NEW: READ FROM DB ---
@app.get("/viz/{viz_id}", response_class=HTMLResponse)
async def get_visualization(
    viz_id: int,
    request: Request,
    share_token: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
):
    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")

    # Permission checks
    is_owner = current_user is not None and viz.user_id == current_user.id
    if not viz.is_public and not is_owner:
        # allow token-based access
        if not share_token or share_token != viz.share_token:
            raise HTTPException(status_code=403, detail="This visualization is private")

    # Audit log
    audit = AuditLog(viz_id=viz.id, user_id=(current_user.id if current_user else None), action="view", ip_address=request.client.host if request.client else None)
    session.add(audit)
    session.commit()

    other_view = "model" if viz.view_type == "head" else "head"
    other_label = "Switch to Model View" if viz.view_type == "head" else "Switch to Head View"
    
    # 3. Render with annotation UI
    return f"""
    <html>
      <head>
        {STYLES}
        <style>
            #annotation-panel {{ margin-top: 2rem; padding: 1rem; border: 1px solid #ddd; border-radius: 5px; }}
            .annotation-item {{ padding: 0.5rem; margin: 0.5rem 0; background: #f0f0f0; border-left: 3px solid #007bff; }}
            .annotation-item .meta {{ font-size: 0.8rem; color: #666; }}
            .token-selected {{ background-color: #ffeb3b; cursor: pointer; }}
            #token-input {{ width: 100%; padding: 8px; margin-bottom: 0.5rem; }}
            #add-annotation-btn {{ padding: 8px 16px; background: #28a745; color: white; border: none; border-radius: 3px; cursor: pointer; }}
            #add-annotation-btn:hover {{ background: #218838; }}
            .delete-annotation {{ font-size: 0.8rem; color: #dc3545; cursor: pointer; margin-left: 1rem; }}
        </style>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.6/require.min.js"></script>
        <script>
          requirejs.config({{
              paths: {{
                  base: '/static/base',
                  "d3": "https://cdnjs.cloudflare.com/ajax/libs/d3/5.7.0/d3.min",
                  jquery: '//ajax.googleapis.com/ajax/libs/jquery/2.0.0/jquery.min',
              }},
          }});
        </script>
        <script>
          let selectedTokens = {{}};
          let allAnnotations = [];
          const VIZ_ID = {viz_id};

          // Load annotations on page load
          async function loadAnnotations() {{
            try {{
              const res = await fetch(`/viz/${{VIZ_ID}}/annotations`);
              if (res.ok) {{
                allAnnotations = await res.json();
                renderAnnotations();
              }}
            }} catch (err) {{
              console.error("Failed to load annotations:", err);
            }}
          }}

          function renderAnnotations() {{
            const panel = document.getElementById('annotations-list');
            if (!panel) return;
            
            panel.innerHTML = '';
            allAnnotations.forEach(ann => {{
              const div = document.createElement('div');
              div.className = 'annotation-item';
              const token_range = `tokens [${{ann.start_token}}:${{ann.end_token}}]`;
              const deleteBtn = '<span class="delete-annotation" onclick="deleteAnnotation(' + ann.id + ')">✕ Delete</span>';
              div.innerHTML = `<strong>${{ann.username}}:</strong> ${{ann.content}} <br/><span class="meta">${{token_range}} · ${{new Date(ann.created_at).toLocaleString()}}</span>${{deleteBtn}}`;
              panel.appendChild(div);
            }});
          }}

          async function addAnnotation() {{
            const textarea = document.getElementById('annotation-input');
            const content = textarea.value.trim();
            if (!content) {{
              alert('Please enter a comment');
              return;
            }}

            const start = document.getElementById('start-token').value;
            const end = document.getElementById('end-token').value;
            
            if (start === '' || end === '') {{
              alert('Please select a token range');
              return;
            }}

            const token = localStorage.getItem('auth_token');
            if (!token) {{
              alert('Please log in first to add annotations');
              return;
            }}

            try {{
              const res = await fetch(`/viz/${{VIZ_ID}}/annotations?content=${{encodeURIComponent(content)}}&start_token=${{start}}&end_token=${{end}}`, {{
                method: 'POST',
                headers: {{
                  'Authorization': `Bearer ${{token}}`
                }}
              }});

              if (res.ok) {{
                textarea.value = '';
                document.getElementById('start-token').value = '';
                document.getElementById('end-token').value = '';
                await loadAnnotations();
              }} else {{
                const error = await res.json();
                alert('Error: ' + error.detail);
              }}
            }} catch (err) {{
              alert('Failed to add annotation: ' + err.message);
            }}
          }}

          async function deleteAnnotation(annotationId) {{
            if (!confirm('Delete this annotation?')) return;
            
            const token = localStorage.getItem('auth_token');
            if (!token) {{
              alert('Please log in to delete annotations');
              return;
            }}

            try {{
              const res = await fetch(`/viz/annotations/${{annotationId}}`, {{
                method: 'DELETE',
                headers: {{
                  'Authorization': `Bearer ${{token}}`
                }}
              }});

              if (res.ok) {{
                await loadAnnotations();
              }} else {{
                const error = await res.json();
                alert('Error: ' + error.detail);
              }}
            }} catch (err) {{
              alert('Failed to delete: ' + err.message);
            }}
          }}

                    function checkLoginStatus() {{
                        const token = localStorage.getItem('auth_token');
                        const username = localStorage.getItem('username');
                        const el = document.getElementById('viz-user-info');
                        if (token && username && el) {{
                            el.style.display = 'inline-block';
                            el.textContent = `Logged in as: ${{username}}`;
                        }} else if (el) {{
                            el.style.display = 'none';
                        }}
                    }}

                    function logoutFromViz() {{
                        localStorage.removeItem('auth_token');
                        localStorage.removeItem('username');
                        checkLoginStatus();
                    }}

                    window.addEventListener('load', function() {{ loadAnnotations(); checkLoginStatus(); }});
        </script>
      </head>
      <body>
        <div class="container">
            <div class="controls">
                <a href="/unload" class="btn btn-secondary">← Back & Clear RAM</a>
                <div id="viz-user-info" style="display:none; margin-left: 1rem; font-weight: bold; color: #155724;"></div>
                
                <form action="/visualize" method="post" style="margin:0;">
                    <input type="hidden" name="model_name" value="{viz.model_name}">
                    <input type="hidden" name="text" value="{viz.input_text}">
                    <input type="hidden" name="view_type" value="{other_view}">
                    <button type="submit" class="btn btn-outline">{other_label}</button>
                </form>
            </div>
            
            <h3 style="text-align:center;">
                Viz ID: #{viz.id} | {viz.model_name} ({viz.view_type})
            </h3>
            
            <!-- Iframe to display the visualization -->
            <iframe 
                src="/viz/{viz_id}/content" 
                style="width: 100%; height: 700px; border: 1px solid #ddd; border-radius: 5px;"
                frameborder="0">
            </iframe>

            <!-- Annotation Panel -->
            <div id="annotation-panel">
                <h4>Collaborative Annotations</h4>
                
                <div style="margin-bottom: 1rem;">
                    <label><strong>Token Range:</strong></label><br/>
                    Start: <input type="number" id="start-token" min="0" style="width: 80px;"> 
                    End: <input type="number" id="end-token" min="0" style="width: 80px;">
                    <small>(Select which tokens to annotate)</small>
                </div>

                <textarea id="annotation-input" placeholder="Add your comment here..." style="width: 100%; height: 60px; padding: 8px; margin-bottom: 0.5rem;"></textarea>
                <button id="add-annotation-btn" onclick="addAnnotation()">Add Comment</button>

                <h5>All Comments:</h5>
                <div id="annotations-list" style="max-height: 300px; overflow-y: auto;">
                    <p style="color: #999;">Loading annotations...</p>
                </div>

                <hr/>
                <p style="font-size: 0.9rem; color: #666;">
                    Not logged in? <a href="#" onclick="showLoginModal()">Click here to log in</a> to add annotations.
                </p>
            </div>
        </div>

        <!-- Simple Login Modal -->
        <div id="login-modal" style="display:none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000;">
            <div style="background: white; padding: 2rem; border-radius: 10px; width: 300px; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);box-shadow: 0 4px 6px rgba(0,0,0,0.2);">
                <h3>Login</h3>
                <input type="text" id="login-username" placeholder="Username" style="width: 100%; padding: 8px; margin-bottom: 0.5rem; box-sizing: border-box;">
                <input type="password" id="login-password" placeholder="Password" style="width: 100%; padding: 8px; margin-bottom: 1rem; box-sizing: border-box;">
                <button onclick="performLogin()" class="btn btn-primary" style="width: 100%; margin-bottom: 0.5rem;">Login</button>
                <button onclick="document.getElementById('login-modal').style.display='none'" class="btn btn-secondary" style="width: 100%;">Close</button>
            </div>
        </div>

        <script>
            function showLoginModal() {{
                document.getElementById('login-modal').style.display = 'block';
            }}

            async function performLogin() {{
                const username = document.getElementById('login-username').value;
                const password = document.getElementById('login-password').value;
                
                if (!username || !password) {{
                    alert('Please fill in all fields');
                    return;
                }}

                try {{
                    const formData = new FormData();
                    formData.append('username', username);
                    formData.append('password', password);

                    const res = await fetch('/auth/login', {{
                        method: 'POST',
                        body: formData
                    }});

    stmt_prev = select(Visualization).where(Visualization.id < viz_id).order_by(Visualization.id.desc())
    prev_viz = session.exec(stmt_prev).first()
    stmt_next = select(Visualization).where(Visualization.id > viz_id).order_by(Visualization.id.asc())
    next_viz = session.exec(stmt_next).first()

    logger.info(json.dumps({"event": "viz_view", "viz_id": viz.id, "user_id": (current_user.id if current_user else None)}))

    return templates.TemplateResponse("viz.html", {
        "request": request,
        "viz": viz,
        "other_view": other_view,
        "other_label": other_label,
        "prev_viz": prev_viz,
        "next_viz": next_viz
    })


@app.get("/viz/{viz_id}/export")
async def export_visualization(viz_id: int, session: Session = Depends(get_session), current_user: Optional[User] = Depends(get_current_user_optional)):
    """Export visualization metadata + annotations as JSON."""
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
    """Return a CSV representation of the visualization + annotations."""
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
    """Return a ZIP containing the HTML, JSON metadata, and CSV export."""
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
    """Owner-only: generate or reset a share_token and optionally make public."""
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
    """Export all visualizations for a user as CSV (owner-only)."""
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