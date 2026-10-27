---
description: Create a dev user in spendly.db with sample expenses
argument-hint: [name] [email]
---
Create a development user in `spendly.db` using the helpers in `database/db.py`.

- Name and email come from: $ARGUMENTS. If none are given, make up a realistic name and an @spendly.com email.
- Password: `password123`, hashed with `generate_password_hash`.
- Add 8 expenses for that user dated this month (none after today), with one expense in each category.
- Use parameterized queries only, and don't modify the demo user.
- If the email already exists, stop and say so.
- Finish by printing the user's id, email, password and expense count.
