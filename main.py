# main.py
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from visualization_logic import get_viz_data, free_memory

app = FastAPI()

# Shared CSS for centering and button styles
STYLES = """
<style>
    body { 
        font-family: sans-serif; 
        background-color: #f4f4f9;
        margin: 0;
        display: flex;
        flex-direction: column;
        align-items: center; /* Centers horizontally */
        min-height: 100vh;
    }
    .container {
        background: white;
        padding: 2rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        width: 90%;
        max-width: 1000px; /* Prevents it from getting too wide */
        margin-top: 2rem;
    }
    textarea { width: 100%; height: 100px; margin-bottom: 1rem; padding: 8px; }
    input[type="text"] { width: 100%; padding: 10px; margin-bottom: 1rem; }
    
    /* Button Styling */
    .btn {
        padding: 10px 20px;
        border: none;
        border-radius: 5px;
        cursor: pointer;
        font-weight: bold;
        text-decoration: none;
        display: inline-block;
        margin-right: 10px;
    }
    .btn-primary { background: #007bff; color: white; }
    .btn-secondary { background: #6c757d; color: white; }
    .btn-outline { border: 1px solid #007bff; color: #007bff; background: white; }
    
    .controls {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
        padding-bottom: 10px;
        border-bottom: 1px solid #eee;
    }
</style>
"""

@app.get("/", response_class=HTMLResponse)
async def home():
    # ... (Home HTML remains the same) ...
    # (See previous response for full HTML if needed)
    return """
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
    """.format(STYLES=STYLES)

# --- NEW ENDPOINT: Unload Memory ---
@app.get("/unload")
async def unload_and_go_home():
    # 1. Dump the model from RAM
    free_memory()
    # 2. Go back to start
    return RedirectResponse(url="/")

@app.post("/visualize", response_class=HTMLResponse)
async def visualize(model_name: str = Form(...), text: str = Form(...), view_type: str = Form("head")):
    
    viz_data = get_viz_data(model_name, text, view_type)
    
    other_view = "model" if view_type == "head" else "head"
    other_label = "Switch to Model View" if view_type == "head" else "Switch to Head View"

    # UPDATED BACK BUTTON: Points to /unload
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
                    <input type="hidden" name="model_name" value="{model_name}">
                    <input type="hidden" name="text" value="{text}">
                    <input type="hidden" name="view_type" value="{other_view}">
                    <button type="submit" class="btn btn-outline">{other_label}</button>
                </form>
            </div>
            <h3 style="text-align:center;">{model_name} ({view_type} view)</h3>
            <div style="width: 100%; display: flex; justify-content: center;">
                {viz_data}
            </div>
        </div>
      </body>
    </html>
    """