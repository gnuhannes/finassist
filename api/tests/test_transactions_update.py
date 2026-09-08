import pytest
from httpx import AsyncClient

from tests.helpers import create_account, create_category, create_transaction


@pytest.mark.asyncio
async def test_patch_transaction_sets_category(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    cat = await create_category(test_app, name="Groceries")
    tx = await create_transaction(test_app, account_id=acc["id"])

    res = await test_app.patch(
        f"/api/transactions/{tx['id']}", json={"category_id": cat["id"]}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["category_id"] == cat["id"]
    assert body["id"] == tx["id"]


@pytest.mark.asyncio
async def test_patch_transaction_clears_category(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    cat = await create_category(test_app, name="Groceries")
    tx = await create_transaction(test_app, account_id=acc["id"])

    # Set category first
    await test_app.patch(
        f"/api/transactions/{tx['id']}", json={"category_id": cat["id"]}
    )

    # Clear it
    res = await test_app.patch(
        f"/api/transactions/{tx['id']}", json={"category_id": None}
    )
    assert res.status_code == 200
    assert res.json()["category_id"] is None


@pytest.mark.asyncio
async def test_patch_transaction_empty_body_keeps_category(
    test_app: AsyncClient,
) -> None:
    acc = await create_account(test_app)
    cat = await create_category(test_app, name="Groceries")
    tx = await create_transaction(test_app, account_id=acc["id"])
    await test_app.patch(
        f"/api/transactions/{tx['id']}", json={"category_id": cat["id"]}
    )

    res = await test_app.patch(f"/api/transactions/{tx['id']}", json={})
    assert res.status_code == 200
    assert res.json()["category_id"] == cat["id"]


@pytest.mark.asyncio
async def test_patch_transaction_not_found(test_app: AsyncClient) -> None:
    res = await test_app.patch("/api/transactions/99999", json={"category_id": None})
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_patch_transaction_invalid_category(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    tx = await create_transaction(test_app, account_id=acc["id"])

    res = await test_app.patch(
        f"/api/transactions/{tx['id']}", json={"category_id": 99999}
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_list_transactions_uncategorized_filter(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    cat = await create_category(test_app, name="Groceries")

    tx_uncat = await create_transaction(
        test_app, account_id=acc["id"], external_id="uncat-1"
    )
    tx_cat = await create_transaction(
        test_app, account_id=acc["id"], external_id="cat-1"
    )

    # Categorize one transaction
    await test_app.patch(
        f"/api/transactions/{tx_cat['id']}", json={"category_id": cat["id"]}
    )

    # Without filter: both returned
    res = await test_app.get("/api/transactions", params={"account_id": acc["id"]})
    assert res.status_code == 200
    assert res.json()["total"] == 2

    # With uncategorized filter: only uncategorized
    res = await test_app.get(
        "/api/transactions",
        params={"account_id": acc["id"], "category_filter": "uncategorized"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == tx_uncat["id"]
