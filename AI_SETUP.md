# CivicPulse AI setup and troubleshooting

## Why AI did not work in the uploaded project

1. The uploaded root `.env` contains `GEMINI_API_KEY=""`, so the backend has no key.
2. `python-dotenv` was not listed in `backend/requirements.txt`. A clean install or deployment therefore did not load `.env`.
3. The frontend API URL was hard-coded to `http://localhost:8000`. In a deployed browser, `localhost` means the visitor's own computer, not the deployed backend.
4. The fallback model was `gemini-1.5-flash`, an obsolete model. It is now `gemini-2.5-flash-lite`.
5. AI routes require a logged-in user. The UI now explains this instead of sending a request that only returns `401 Not authenticated`.
6. Cross-domain production cookies need HTTPS, `COOKIE_SECURE=true`, and `COOKIE_SAMESITE=none`.

## Local setup on Windows PowerShell

Run these commands from the `CIVICPULSE_FINAL` folder:

```powershell
Copy-Item .env.example .env
notepad .env
```

Replace only this placeholder with the key created in Google AI Studio:

```env
GEMINI_API_KEY="your_real_key_here"
```

Quotes are optional, but keeping the double quotes is valid. Do not add spaces around `=`.

Create a fresh virtual environment. Do not reuse or upload the included old `venv` folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

In a second PowerShell terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, sign up or log in, and then use voice transcription or **Analyze Report with AI**.

## Verify the backend before opening the frontend

Open this URL in the browser:

```text
http://localhost:8000/ai/health
```

Expected result:

```json
{"ai_available":true,"message":"AI service is configured."}
```

This proves that the key and Python package are detected. The first real analysis request also verifies that Google accepts the key and that quota is available.

## Deployment settings

Set these variables on the backend service (Railway, Render, or another host):

```env
GEMINI_API_KEY="your_real_key_here"
GEMINI_MODEL="gemini-2.5-flash"
GEMINI_FALLBACK_MODEL="gemini-2.5-flash-lite"
GEMINI_STT_MODEL="gemini-2.5-flash"
COOKIE_SECURE="true"
COOKIE_SAMESITE="none"
```

Do not rely on uploading a `.env` file to production. Add each value in the host's environment-variable settings.

Set this variable on the frontend service before building:

```env
VITE_API_URL="https://your-real-backend-domain.example"
```

Vite inserts `VITE_API_URL` during `npm run build`, so rebuild/redeploy the frontend after changing it.

Recommended backend start command:

```text
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

## What an error now means

- `AI service is not configured`: `GEMINI_API_KEY` is missing/blank or `.env` is in the wrong folder.
- `AI dependency is missing`: reinstall `backend/requirements.txt` in the active Python environment.
- `Gemini rejected the API key`: the key is invalid, restricted incorrectly, or the Gemini API is unavailable for that project.
- `quota or rate limit was reached`: check the API key's quota/billing limits.
- `configured Gemini model is unavailable`: verify the three model environment variables.
- `Not authenticated`: log in before using AI features.
- Browser `Failed to fetch`: check `VITE_API_URL`, HTTPS, backend availability, and cookie settings.
