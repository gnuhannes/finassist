from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers import create_account, create_transaction


@pytest.mark.asyncio
async def test_search_by_payee(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    await create_transaction(
        test_app, account_id=acc["id"], payee="REWE Markt", external_id="s1"
    )
    await create_transaction(
        test_app, account_id=acc["id"], payee="Aldi", external_id="s2"
    )

    res = await test_app.get(
        "/api/transactions", params={"account_id": acc["id"], "q": "rewe"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["payee"] == "REWE Markt"


@pytest.mark.asyncio
async def test_search_case_insensitive(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    await create_transaction(
        test_app, account_id=acc["id"], payee="Amazon.de", external_id="s3"
    )

    for q in ["amazon", "AMAZON", "Amazon"]:
        res = await test_app.get(
            "/api/transactions", params={"account_id": acc["id"], "q": q}
        )
        assert res.status_code == 200
        assert res.json()["total"] == 1, f"Expected 1 result for q={q!r}"


@pytest.mark.asyncio
async def test_search_by_purpose(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    await create_transaction(
        test_app,
        account_id=acc["id"],
        payee="Bank",
        purpose="Monthly rent payment",
        external_id="s4",
    )
    await create_transaction(
        test_app,
        account_id=acc["id"],
        payee="Bank",
        purpose="Utility bill",
        external_id="s5",
    )

    res = await test_app.get(
        "/api/transactions", params={"account_id": acc["id"], "q": "rent"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["purpose"] == "Monthly rent payment"


@pytest.mark.asyncio
async def test_search_no_match(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    await create_transaction(
        test_app, account_id=acc["id"], payee="REWE", external_id="s6"
    )

    res = await test_app.get(
        "/api/transactions", params={"account_id": acc["id"], "q": "zzznomatch"}
    )
    assert res.status_code == 200
    assert res.json()["total"] == 0
    assert res.json()["items"] == []


@pytest.mark.asyncio
async def test_amount_min(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    await create_transaction(
        test_app, account_id=acc["id"], amount="-50.00", external_id="s7"
    )
    await create_transaction(
        test_app, account_id=acc["id"], amount="-200.00", external_id="s8"
    )

    res = await test_app.get(
        "/api/transactions", params={"account_id": acc["id"], "amount_min": "-100.00"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["amount"] == "-50.00"


@pytest.mark.asyncio
async def test_amount_max(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    await create_transaction(
        test_app, account_id=acc["id"], amount="-50.00", external_id="s9"
    )
    await create_transaction(
        test_app, account_id=acc["id"], amount="-200.00", external_id="s10"
    )

    res = await test_app.get(
        "/api/transactions", params={"account_id": acc["id"], "amount_max": "-100.00"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["amount"] == "-200.00"


@pytest.mark.asyncio
async def test_amount_range(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    await create_transaction(
        test_app, account_id=acc["id"], amount="-10.00", external_id="s11"
    )
    await create_transaction(
        test_app, account_id=acc["id"], amount="-50.00", external_id="s12"
    )
    await create_transaction(
        test_app, account_id=acc["id"], amount="-200.00", external_id="s13"
    )

    res = await test_app.get(
        "/api/transactions",
        params={
            "account_id": acc["id"],
            "amount_min": "-100.00",
            "amount_max": "-20.00",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["amount"] == "-50.00"


@pytest.mark.asyncio
async def test_all_accounts(test_app: AsyncClient) -> None:
    acc1 = await create_account(test_app, name="Checking")
    acc2 = await create_account(test_app, name="Savings")
    await create_transaction(
        test_app, account_id=acc1["id"], payee="REWE", external_id="s14"
    )
    await create_transaction(
        test_app, account_id=acc2["id"], payee="Aldi", external_id="s15"
    )

    res = await test_app.get("/api/transactions")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_account_id_still_filters(test_app: AsyncClient) -> None:
    acc1 = await create_account(test_app, name="Checking")
    acc2 = await create_account(test_app, name="Savings")
    await create_transaction(test_app, account_id=acc1["id"], external_id="s16")
    await create_transaction(test_app, account_id=acc2["id"], external_id="s17")

    res = await test_app.get("/api/transactions", params={"account_id": acc1["id"]})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["account_id"] == acc1["id"]


@pytest.mark.asyncio
async def test_search_combined_with_account(test_app: AsyncClient) -> None:
    acc1 = await create_account(test_app, name="Checking")
    acc2 = await create_account(test_app, name="Savings")
    await create_transaction(
        test_app, account_id=acc1["id"], payee="REWE", external_id="s18"
    )
    await create_transaction(
        test_app, account_id=acc2["id"], payee="REWE", external_id="s19"
    )

    res = await test_app.get(
        "/api/transactions", params={"account_id": acc1["id"], "q": "rewe"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["account_id"] == acc1["id"]


@pytest.mark.asyncio
async def test_filter_by_category_id(test_app: AsyncClient) -> None:
    from tests.helpers import create_category

    acc = await create_account(test_app)
    food = await create_category(test_app, name="Food")
    rent = await create_category(test_app, name="Rent")
    t1 = await create_transaction(test_app, account_id=acc["id"], external_id="c1")
    await create_transaction(test_app, account_id=acc["id"], external_id="c2")
    await test_app.patch(
        f"/api/transactions/{t1['id']}", json={"category_id": food["id"]}
    )

    res = await test_app.get(
        "/api/transactions", params={"category_filter": str(food["id"])}
    )
    assert res.status_code == 200
    assert res.json()["total"] == 1

    empty = await test_app.get(
        "/api/transactions", params={"category_filter": str(rent["id"])}
    )
    assert empty.json()["total"] == 0


@pytest.mark.asyncio
async def test_invalid_category_filter_is_422(test_app: AsyncClient) -> None:
    res = await test_app.get(
        "/api/transactions", params={"category_filter": "not-a-thing"}
    )
    assert res.status_code == 422
