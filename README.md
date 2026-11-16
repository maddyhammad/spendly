# Spendly

A Flask and SQLite personal expense tracker with registration, login, and user-owned expenses.

## Run locally

From this directory, with the workspace virtual environment activated:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open http://localhost:5001. Direct startup initializes/migrates `spendly.db` and adds demo data once. The demo login is `demo@spendly.com` / `demo123`.

The dashboard summarizes the current calendar month. Expense history includes all dates, newest first. Add, edit, and delete expenses from the dashboard. Deletion requires confirmation. Expense forms validate amounts, dates, categories, and description length, and require a session form token. Each user's expenses are private to their account.

Set the `SECRET_KEY` environment variable to a persistent random secret to retain sessions across restarts. The direct startup command runs Flask's development server with debugging enabled; use it for local development.

## Tests

```powershell
python -m pytest tests -q
```

Tests use temporary databases and do not modify the local application database.
