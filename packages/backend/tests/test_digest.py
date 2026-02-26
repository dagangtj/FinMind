"""Tests for the weekly digest feature."""

from datetime import date, timedelta


def _create_expense(client, auth_header, amount, description, spent_at, expense_type="EXPENSE", category_id=None):
    """Helper to create an expense."""
    payload = {
        "amount": amount,
        "description": description,
        "date": spent_at.isoformat(),
        "expense_type": expense_type,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201, f"create expense failed: {r.get_json()}"
    return r.get_json()


def _create_category(client, auth_header, name):
    """Helper to create a category."""
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (200, 201), f"create category failed: {r.get_json()}"
    return r.get_json()["id"]


def _get_monday_of_current_week():
    """Return the Monday of the current ISO week."""
    today = date.today()
    return today - timedelta(days=today.weekday())


class TestWeeklyDigestEndpoint:
    """Tests for GET /digest/weekly."""

    def test_empty_digest(self, client, auth_header):
        """Digest with no transactions returns valid structure."""
        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()

        assert "period" in data
        assert "summary" in data
        assert "trends" in data
        assert "category_breakdown" in data
        assert "daily_spending" in data
        assert "top_transactions" in data
        assert "insights" in data

        assert data["summary"]["total_income"] == 0
        assert data["summary"]["total_expenses"] == 0
        assert data["summary"]["net_flow"] == 0
        assert data["summary"]["transaction_count"] == 0

    def test_digest_with_expenses(self, client, auth_header):
        """Digest correctly summarizes expenses in the current week."""
        monday = _get_monday_of_current_week()
        iso = monday.isocalendar()

        _create_expense(client, auth_header, 50.00, "Groceries", monday)
        _create_expense(client, auth_header, 30.00, "Transport", monday + timedelta(days=1))
        _create_expense(client, auth_header, 200.00, "Salary", monday, expense_type="INCOME")

        r = client.get(
            f"/digest/weekly?year={iso[0]}&week={iso[1]}",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()

        assert data["summary"]["total_expenses"] == 80.0
        assert data["summary"]["total_income"] == 200.0
        assert data["summary"]["net_flow"] == 120.0
        assert data["summary"]["transaction_count"] == 3

    def test_digest_with_category_breakdown(self, client, auth_header):
        """Digest includes per-category breakdown."""
        monday = _get_monday_of_current_week()
        iso = monday.isocalendar()

        cat_food = _create_category(client, auth_header, "Food")
        cat_transport = _create_category(client, auth_header, "Transport")

        _create_expense(client, auth_header, 100.00, "Restaurant", monday, category_id=cat_food)
        _create_expense(client, auth_header, 40.00, "Bus pass", monday + timedelta(days=2), category_id=cat_transport)

        r = client.get(
            f"/digest/weekly?year={iso[0]}&week={iso[1]}",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()

        cats = data["category_breakdown"]
        assert len(cats) == 2
        # Sorted by amount desc
        assert cats[0]["category_name"] == "Food"
        assert cats[0]["amount"] == 100.0
        assert cats[1]["category_name"] == "Transport"
        assert cats[1]["amount"] == 40.0
        # Share percentages
        assert cats[0]["share_pct"] > 0
        assert abs(cats[0]["share_pct"] + cats[1]["share_pct"] - 100.0) < 0.2

    def test_digest_trends_with_previous_week(self, client, auth_header):
        """Digest computes week-over-week trends."""
        monday = _get_monday_of_current_week()
        prev_monday = monday - timedelta(weeks=1)
        iso = monday.isocalendar()

        # Previous week: $100 expenses
        _create_expense(client, auth_header, 100.00, "Last week groceries", prev_monday)
        # Current week: $150 expenses
        _create_expense(client, auth_header, 150.00, "This week groceries", monday)

        r = client.get(
            f"/digest/weekly?year={iso[0]}&week={iso[1]}",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()

        assert data["trends"]["prev_week_expenses"] == 100.0
        assert data["trends"]["expense_change_pct"] == 50.0

    def test_digest_generates_insights(self, client, auth_header):
        """Digest generates human-readable insights."""
        monday = _get_monday_of_current_week()
        prev_monday = monday - timedelta(weeks=1)
        iso = monday.isocalendar()

        _create_expense(client, auth_header, 80.00, "Prev week spend", prev_monday)
        _create_expense(client, auth_header, 120.00, "This week spend", monday)

        r = client.get(
            f"/digest/weekly?year={iso[0]}&week={iso[1]}",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()

        assert len(data["insights"]) > 0
        # Should mention spending increase
        assert any("increased" in i.lower() for i in data["insights"])

    def test_digest_daily_spending(self, client, auth_header):
        """Digest includes daily spending breakdown."""
        monday = _get_monday_of_current_week()
        iso = monday.isocalendar()

        _create_expense(client, auth_header, 25.00, "Monday lunch", monday)
        _create_expense(client, auth_header, 75.00, "Tuesday dinner", monday + timedelta(days=1))

        r = client.get(
            f"/digest/weekly?year={iso[0]}&week={iso[1]}",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()

        daily = data["daily_spending"]
        assert len(daily) == 2
        assert daily[0]["date"] == monday.isoformat()
        assert daily[0]["amount"] == 25.0
        assert daily[1]["amount"] == 75.0

    def test_digest_top_transactions(self, client, auth_header):
        """Digest returns top transactions by amount."""
        monday = _get_monday_of_current_week()
        iso = monday.isocalendar()

        _create_expense(client, auth_header, 10.00, "Coffee", monday)
        _create_expense(client, auth_header, 500.00, "Rent", monday + timedelta(days=1))
        _create_expense(client, auth_header, 50.00, "Groceries", monday + timedelta(days=2))

        r = client.get(
            f"/digest/weekly?year={iso[0]}&week={iso[1]}",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()

        top = data["top_transactions"]
        assert len(top) == 3
        assert top[0]["amount"] == 500.0
        assert top[0]["description"] == "Rent"

    def test_digest_invalid_week(self, client, auth_header):
        """Invalid week number returns 400."""
        r = client.get("/digest/weekly?week=55", headers=auth_header)
        assert r.status_code == 400

    def test_digest_invalid_params(self, client, auth_header):
        """Non-numeric params return 400."""
        r = client.get("/digest/weekly?year=abc", headers=auth_header)
        assert r.status_code == 400

    def test_digest_requires_auth(self, client):
        """Endpoint requires authentication."""
        r = client.get("/digest/weekly")
        assert r.status_code == 401


class TestWeeklyDigestService:
    """Unit tests for the digest service internals."""

    def test_week_bounds(self):
        """_week_bounds returns correct Monday-Sunday range."""
        from app.services.weekly_digest import _week_bounds

        # 2026-W01 starts on Monday Dec 29, 2025
        monday, sunday = _week_bounds(2026, 1)
        assert monday.weekday() == 0  # Monday
        assert sunday.weekday() == 6  # Sunday
        assert (sunday - monday).days == 6

    def test_prev_week(self):
        """_prev_week correctly computes previous week."""
        from app.services.weekly_digest import _prev_week

        y, w = _prev_week(2026, 5)
        assert w == 4
        assert y == 2026

        # Week 1 wraps to previous year
        y, w = _prev_week(2026, 1)
        assert y == 2025

    def test_pct_change(self):
        """_pct_change handles normal and edge cases."""
        from app.services.weekly_digest import _pct_change

        assert _pct_change(150, 100) == 50.0
        assert _pct_change(80, 100) == -20.0
        assert _pct_change(100, 0) is None
        assert _pct_change(0, 0) is None

    def test_generate_insights_no_prev_data(self):
        """Insights handle missing previous week gracefully."""
        from app.services.weekly_digest import _generate_insights

        insights = _generate_insights(100.0, 0.0, [], [], [])
        assert len(insights) >= 1
        assert "$100.00" in insights[0]
