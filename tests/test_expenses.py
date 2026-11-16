from datetime import date, timedelta
import pytest
from database.db import get_db, get_profile_data
from tests.test_auth import sign_up_and_log_in, register, login


def submit(client, path='/expenses/add', **changes):
    client.get(path)
    with client.session_transaction() as session:
        token = session['expense_csrf']
    data = dict(amount='12.50', category='Food', date=date.today().isoformat(),
                description='Lunch', csrf_token=token)
    data.update(changes)
    return client.post(path, data=data)


def test_expense_lifecycle(app, client):
    sign_up_and_log_in(client)
    assert 'No expenses yet.' in client.get('/profile').text
    assert submit(client).status_code == 302
    page = client.get('/profile').text
    assert 'Lunch' in page and '₹12.50' in page and 'Sample data' not in page
    with app.app_context():
        expense_id = get_db().execute('SELECT id FROM expenses').fetchone()['id']
    assert submit(client, f'/expenses/{expense_id}/edit', amount='25.00', description='Dinner').status_code == 302
    assert 'Dinner' in client.get('/profile').text
    path = f'/expenses/{expense_id}/delete'
    assert client.get(path).status_code == 200
    assert 'Dinner' in client.get('/profile').text
    assert submit(client, path).status_code == 302
    assert 'No expenses yet.' in client.get('/profile').text


@pytest.mark.parametrize('changes', [
    {'amount': 'NaN'}, {'amount': 'Infinity'}, {'amount': '0'},
    {'amount': '-1'}, {'amount': '1.001'}, {'amount': '1000000000'},
    {'amount': ''}, {'category': 'Invalid'}, {'date': 'invalid'},
    {'date': (date.today() + timedelta(days=1)).isoformat()},
    {'description': 'x' * 501},
])
def test_invalid_expense_never_saved(app, client, changes):
    sign_up_and_log_in(client)
    assert submit(client, **changes).status_code == 400
    with app.app_context():
        assert get_db().execute('SELECT COUNT(*) FROM expenses').fetchone()[0] == 0


def test_expense_token_required(app, client):
    sign_up_and_log_in(client)
    assert client.post('/expenses/add', data={'amount': '12'}).status_code == 400
    submit(client)
    for path in ['/expenses/1/edit', '/expenses/1/delete']:
        assert client.post(path, data={'csrf_token': 'wrong'}).status_code == 400
    with app.app_context():
        assert get_db().execute('SELECT COUNT(*) FROM expenses').fetchone()[0] == 1


def test_other_users_cannot_access_expenses(app, client):
    sign_up_and_log_in(client)
    submit(client, description='Private lunch')
    client.post('/logout')
    register(client, email='other@example.com')
    login(client, email='other@example.com')
    assert 'Private lunch' not in client.get('/profile').text
    for path in ['/expenses/1/edit', '/expenses/1/delete', '/expenses/999/edit']:
        assert client.get(path).status_code == 404
        assert client.post(path).status_code == 404


def test_monthly_summary_and_full_history(app, client):
    sign_up_and_log_in(client)
    old_date = date.today().replace(day=1) - timedelta(days=1)
    submit(client, amount='100', date=old_date.isoformat(), description='Older expense')
    submit(client, amount='30', category='Food')
    submit(client, amount='70', category='Bills')
    with app.app_context():
        user_id = get_db().execute('SELECT id FROM users').fetchone()[0]
        data = get_profile_data(user_id)
        assert data['summary'] == dict(total=100, count=2, top_category='Bills', top_amount=70)
        assert data['category_totals'][0]['share'] == 70
        assert len(data['recent_expenses']) == 3
    assert 'Older expense' in client.get('/profile').text


def test_expense_description_is_escaped(client):
    sign_up_and_log_in(client)
    submit(client, description='<script>alert(1)</script>')
    page = client.get('/profile').text
    assert '<script>alert(1)</script>' not in page
    assert '&lt;script&gt;' in page
