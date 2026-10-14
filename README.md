# CV Maker (FastAPI + React)
CV Maker (FastAPI + React/TypeScript)

Live Demo: https://cv-maker-application.onrender.com/

## Local development
Backend:  cd backend && pip install -r requirements.txt
          export ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=strong-password JWT_SECRET=$(openssl rand -hex 32)
          uvicorn main:app --reload            # API docs: http://localhost:8000/docs
Frontend: cd frontend && npm install && npm run dev   # http://localhost:5173

## Production
One Docker image serves the API and the UI (see Dockerfile).
- Render:  push to GitHub, then New > Blueprint (render.yaml). Set ADMIN_EMAIL and ADMIN_PASSWORD.
- VPS:     create .env (JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, DB_PASSWORD), edit Caddyfile domain,
           point your domain's DNS A record at the server, run: docker compose up -d --build

## Free + secure options
1. Oracle Cloud Always Free VM (never sleeps, data persists): install Docker, use docker-compose.yml + Caddyfile.
   Get a free domain from duckdns.org, put it in Caddyfile; open ports 80 and 443 in the VM's firewall.
2. Render free web service (sleeps after ~15 min idle) + a free hosted Postgres (e.g. Neon): use render.yaml,
   paste the Postgres connection string as DATABASE_URL.

Note: after updating, run `pip install -r backend/requirements.txt` again (PDF import needs pdfminer.six and python-multipart).

