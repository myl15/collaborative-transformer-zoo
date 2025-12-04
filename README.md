# collaborative-transformer-zoo
A web-based platform designed to demystify and collaboratively explore the internal workings of deep learning models. 

## Project Details
The *Collaborative Transformer Zoo* is a web-based platform designed to demystify and collaboratively explore the internal workings of Natural Language Processing deep learning models. Its primary purpose is to transform the currently isolated and code-heavy process of model interpretability into a shared, interactive and persistent experience.

### Project Goals
Our main goal is to enable researchers to:
- Visualize Internal States: Submit text and generate interactive visualizations of model internals from various Transformer models.
- Saving and Sharing: Permanently store these visualizations in a database, creating unique, shareable links.
- Annotation and Collaboration: Add comments and insights directly onto specific parts of visualizations, fostering a community-driven understanding of complex models.

## Initial Project Design
The following diagrams represent the initial design for the project. 
### Initial ERD
![ERD Diagram](assets/Project_ERD.png)

### Initial System Design Flow
![System Design Flow Diagram](assets/SystemDesignFlow.png)

### Initial Goals
- Week 1:
    - Build Core API that can run a model and render a static visualization
- Week 2:
    - Implement Database schema
    - Build the save and view functionality
- Week 3:
    - Add user authentication and the annotations table
    - Implement the commenting feature
- Week 4:
    - Implement Redis caching
    - Finalize demo and report

## Running Current Demo of Visualization Webpage

### Prerequisites
1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment variables:**
   - Copy `.env.example` to `.env`
   - Add your HuggingFace token: `HF_TOKEN=<your_token>`
   - Update `SECRET_KEY` with a secure random string (for JWT authentication)

3. **Start PostgreSQL via Docker:**
   ```bash
   docker-compose up -d
   ```

4. **Run the server:**
   ```bash
   uvicorn main:app --reload
   ```

   The app will be available at `http://localhost:8000`

### Features

#### Core Visualization
- Submit model name and text input
- Choose between "Head View" (attention head detail) or "Model View" (layer-wise blocks)
- View interactive attention patterns using BertViz
- Persistent storage with unique shareable URLs

#### User Authentication
- **Sign up:** POST `/auth/signup` with username, email, password
- **Login:** POST `/auth/login` with username, password
- Returns JWT token (valid for 24 hours by default)
- Token stored in browser's localStorage for authenticated requests

#### Collaborative Annotations
- **Add annotations:** Select token range, add comment (requires login)
  - POST `/viz/{id}/annotations?content=...&start_token=...&end_token=...`
  - Header: `Authorization: Bearer <token>`
- **View all annotations:** GET `/viz/{id}/annotations`
- **Edit own annotations:** PATCH `/viz/annotations/{id}?content=...`
- **Delete own annotations:** DELETE `/viz/annotations/{id}`
- Ownership verification: only annotation authors can edit/delete
- Timestamps track creation and updates

#### Production Hardening
- **Rate Limiting:** 5 requests/minute per IP on `/visualize` endpoint
  - Prevents GPU exhaustion from spam/DoS attacks
  - Returns HTTP 429 when limit exceeded
- **Input Validation:** Pydantic-based sanitization
  - Blocks path traversal (`../`, leading `/`)
  - Blocks SQL injection (`';--`)
  - Blocks XSS attacks (`<script>`)
  - Validates model names, text length, view types
- **Redis Caching:** 1-hour TTL on inference results
  - Caches expensive GPU computations
  - 50-240x faster response times for cache hits
  - `/cache/stats` endpoint shows cache metrics
  - `/cache/clear` endpoint allows manual cache clearing

## Docker Desktop Setup
To create a stateful application with a postgres database, we used a docker environment which is built using `docker-compose.yml`. Before running the `uvicorn` app, make sure to open the docker desktop application and run `docker-compose up -d` in your terminal from the main folder.