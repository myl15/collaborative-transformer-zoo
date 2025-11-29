# main.py
from fastapi import FastAPI, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from contextlib import asynccontextmanager

# Import our new modules
from visualization_logic import get_viz_data, free_memory
from database import create_db_and_tables, get_session
from models import Visualization

# Redefine Styles if not exported from core_logic
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

# Lifecycle: Run this when server starts
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables() # <--- Creates tables in Postgres
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
async def home():
    return f"""
    <html>
        <head><title>Transformer Zoo</title>{STYLES}</head>
        <body>
            <div class="container">
                <h1>Collaborative Transformer Zoo</h1>
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
        </body>
    </html>
    """

@app.get("/unload")
async def unload_and_go_home():
    free_memory()
    return RedirectResponse(url="/")

# --- NEW: WRITE TO DB ---
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
async def get_visualization(viz_id: int, session: Session = Depends(get_session)):
    # 1. Fetch from DB
    viz = session.get(Visualization, viz_id)
    if not viz:
        raise HTTPException(status_code=404, detail="Visualization not found")
        
    # 2. Determine "Switch View" logic
    other_view = "model" if viz.view_type == "head" else "head"
    other_label = "Switch to Model View" if viz.view_type == "head" else "Switch to Head View"
    
    # 3. Render
    return f"""
    <html>
      <head>
        {STYLES}
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
      </head>
      <body>
        <div class="container">
            <div class="controls">
                <a href="/unload" class="btn btn-secondary">← Back & Clear RAM</a>
                
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
            
            <div style="width: 100%; display: flex; justify-content: center;">
                {viz.html_content}
            </div>
        </div>
      </body>
    </html>
    """