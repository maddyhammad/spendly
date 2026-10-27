---
description: Add sample expenses for an existing user in spendly.db
argument-hint: [email] [count]
---
Add sample expenses for an existing user in `spendly.db`, using the helpers in `database/db.py`.

- Arguments: $ARGUMENTS. First the user's email, then how many expenses to add (default 5). If no email is given, use demo@spendly.com.
- If the user doesn't exist, stop and say so.
- Categories must come from `CATEGORIES` in `database/db.py`. Amounts are positive and realistic, and every expense has a description.
- Dates are this month, none after today, formatted YYYY-MM-DD.
- Use parameterized queries only, and insert everything in one transaction that rolls back on error.
- Finish by printing the added expenses and the user's new total expense count.
