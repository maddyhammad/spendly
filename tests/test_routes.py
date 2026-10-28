import pytest


@pytest.mark.parametrize("path", ["/", "/register", "/login", "/terms", "/privacy"])
def test_public_page_renders(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert "Spendly" in response.get_data(as_text=True)


def test_footer_links_point_to_terms_and_privacy(client):
    html = client.get("/").get_data(as_text=True)
    assert 'href="/terms"' in html
    assert 'href="/privacy"' in html


def test_auth_forms_post_to_their_own_routes(client):
    assert 'action="/register"' in client.get("/register").get_data(as_text=True)
    assert 'action="/login"' in client.get("/login").get_data(as_text=True)


@pytest.mark.parametrize(
    "path, step",
    [
        ("/expenses/add", "Step 7"),
        ("/expenses/1/edit", "Step 8"),
        ("/expenses/1/delete", "Step 9"),
    ],
)
def test_stub_routes_unchanged(client, path, step):
    response = client.get(path)
    assert response.status_code == 200
    assert step in response.get_data(as_text=True)
