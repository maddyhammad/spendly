"""Fixed sample figures for the Step 4 profile page design. No database access.

The numbers mirror the seeded demo user's 8 expenses (database/db.py SAMPLE_EXPENSES),
so Step 6 can check its real queries against the same totals for the demo user.

Step 6 replaces get_profile_sample() with queries in database/db.py and deletes this
module. Keep the keys and shapes, and profile.html needs no changes. Only app.profile()
imports this. Avoid key names that are dict methods (items, keys, values): Jinja's
dot lookup would find the method instead.
"""


def get_profile_sample():
    """Return the template context for profile.html (a new dict on every call)."""
    return {
        "period_label": "October 2026",
        "summary": {"total": 7267.00, "count": 8, "top_category": "Bills", "top_amount": 2499.00},
        # Highest amount first; share = whole-number % of summary["total"].
        "category_totals": [
            {"category": "Bills", "amount": 2499.00, "share": 34},
            {"category": "Shopping", "amount": 1899.00, "share": 26},
            {"category": "Food", "amount": 1100.00, "share": 15},
            {"category": "Health", "amount": 850.00, "share": 12},
            {"category": "Entertainment", "amount": 499.00, "share": 7},
            {"category": "Other", "amount": 300.00, "share": 4},
            {"category": "Transport", "amount": 120.00, "share": 2},
        ],
        # Newest first, at most 5. ISO date strings, like expenses.date.
        "recent_expenses": [
            {"date": "2026-10-26", "description": "Dinner with friends", "category": "Food", "amount": 650.00},
            {"date": "2026-10-22", "description": "Gift wrapping", "category": "Other", "amount": 300.00},
            {"date": "2026-10-19", "description": "New shoes", "category": "Shopping", "amount": 1899.00},
            {"date": "2026-10-15", "description": "Movie tickets", "category": "Entertainment", "amount": 499.00},
            {"date": "2026-10-12", "description": "Pharmacy", "category": "Health", "amount": 850.00},
        ],
    }
