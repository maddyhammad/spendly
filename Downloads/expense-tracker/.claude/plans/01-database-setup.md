# Database Setup Implementation Plan

## Overview

Implement SQLite persistence for the expense tracker.

## Target Files
- database/db.py – database helper module.
- app.py – add DB initialization command.
- .claude/plans/01-database-setup.md – this plan file.

## Steps

1. Create database/db.py with:
   - get_db(): open sqlite3 connection, enable foreign keys, store in flask.g.
   - init_db(): create tables users, categories, expenses.
   - seed_db(): insert sample users and categories (idempotent).

2. Add CLI command in app.py:
   ```bash
   @app.cli.command('init-db')
   def init_db_command():
       '''Create the database tables'''
       from database.db import init_db
       init_db()
       print('Initialized the database!')
   ```

3. Write unit tests in tests/test_db.py:
   - Test get_db returns persistent connection.
   - Test init_db actually creates tables.
   - Test seed_db inserts sample data.

4. Update CLAUDE.md under “Tech constraints” with note that all DB logic lives in database/db.py and uses get_db().

5. Commit changes after tests pass.

This plan covers all steps needed for database setup.
