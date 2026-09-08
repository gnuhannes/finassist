from decimal import Decimal

from my_private_finances.models import CategorizationRule, Transaction
from my_private_finances.services.categorization import match_transaction


def _tx(
    *,
    payee: str | None = None,
    purpose: str | None = None,
    amount: Decimal = Decimal("10.00"),
) -> Transaction:
    return Transaction(
        account_id=1,
        booking_date="2026-01-15",
        amount=amount,
        currency="EUR",
        payee=payee,
        purpose=purpose,
        import_hash="dummy",
    )


def _rule(
    *,
    position: int = 1,
    field: str = "payee",
    operator: str = "contains",
    value: str = "rewe",
    category_id: int = 1,
) -> CategorizationRule:
    return CategorizationRule(
        id=position,
        position=position,
        field=field,
        operator=operator,
        value=value,
        category_id=category_id,
    )


class TestTextContains:
    def test_payee_contains_match(self) -> None:
        tx = _tx(payee="REWE Supermarkt")
        rule = _rule(field="payee", operator="contains", value="rewe")
        assert match_transaction(tx, [rule]) == 1

    def test_payee_contains_no_match(self) -> None:
        tx = _tx(payee="Aldi Nord")
        rule = _rule(field="payee", operator="contains", value="rewe")
        assert match_transaction(tx, [rule]) is None

    def test_purpose_contains_match(self) -> None:
        tx = _tx(purpose="Amazon Marketplace Order")
        rule = _rule(field="purpose", operator="contains", value="amazon")
        assert match_transaction(tx, [rule]) == 1


class TestTextExact:
    def test_exact_match_case_insensitive(self) -> None:
        tx = _tx(payee="REWE")
        rule = _rule(operator="exact", value="rewe")
        assert match_transaction(tx, [rule]) == 1

    def test_exact_no_match(self) -> None:
        tx = _tx(payee="REWE Supermarkt")
        rule = _rule(operator="exact", value="rewe")
        assert match_transaction(tx, [rule]) is None


class TestTextStartsWith:
    def test_starts_with_match(self) -> None:
        tx = _tx(payee="REWE Supermarkt")
        rule = _rule(operator="starts_with", value="rewe")
        assert match_transaction(tx, [rule]) == 1

    def test_starts_with_no_match(self) -> None:
        tx = _tx(payee="Der REWE Markt")
        rule = _rule(operator="starts_with", value="rewe")
        assert match_transaction(tx, [rule]) is None


class TestTextEndsWith:
    def test_ends_with_match(self) -> None:
        tx = _tx(payee="Der REWE")
        rule = _rule(operator="ends_with", value="rewe")
        assert match_transaction(tx, [rule]) == 1


class TestAmountOperators:
    def test_gt(self) -> None:
        tx = _tx(amount=Decimal("100.00"))
        rule = _rule(field="amount", operator="gt", value="50")
        assert match_transaction(tx, [rule]) == 1

    def test_gt_no_match(self) -> None:
        tx = _tx(amount=Decimal("30.00"))
        rule = _rule(field="amount", operator="gt", value="50")
        assert match_transaction(tx, [rule]) is None

    def test_lt(self) -> None:
        tx = _tx(amount=Decimal("-50.00"))
        rule = _rule(field="amount", operator="lt", value="0")
        assert match_transaction(tx, [rule]) == 1

    def test_eq(self) -> None:
        tx = _tx(amount=Decimal("42.00"))
        rule = _rule(field="amount", operator="eq", value="42.00")
        assert match_transaction(tx, [rule]) == 1

    def test_gte(self) -> None:
        tx = _tx(amount=Decimal("50.00"))
        rule = _rule(field="amount", operator="gte", value="50")
        assert match_transaction(tx, [rule]) == 1

    def test_lte(self) -> None:
        tx = _tx(amount=Decimal("50.00"))
        rule = _rule(field="amount", operator="lte", value="50")
        assert match_transaction(tx, [rule]) == 1


class TestFirstMatchWins:
    def test_first_rule_wins(self) -> None:
        tx = _tx(payee="REWE Supermarkt")
        r1 = _rule(position=1, value="rewe", category_id=10)
        r2 = _rule(position=2, value="supermarkt", category_id=20)
        assert match_transaction(tx, [r1, r2]) == 10

    def test_second_rule_if_first_does_not_match(self) -> None:
        tx = _tx(payee="Aldi Supermarkt")
        r1 = _rule(position=1, value="rewe", category_id=10)
        r2 = _rule(position=2, value="supermarkt", category_id=20)
        assert match_transaction(tx, [r1, r2]) == 20


class TestNoneFields:
    def test_none_payee_does_not_match(self) -> None:
        tx = _tx(payee=None)
        rule = _rule(field="payee", operator="contains", value="rewe")
        assert match_transaction(tx, [rule]) is None

    def test_no_rules_returns_none(self) -> None:
        tx = _tx(payee="REWE")
        assert match_transaction(tx, []) is None


class TestEdgeCases:
    def test_unknown_text_operator_returns_none(self) -> None:
        tx = _tx(payee="REWE")
        rule = _rule(operator="unknown_op", value="rewe")
        assert match_transaction(tx, [rule]) is None

    def test_unknown_amount_operator_returns_none(self) -> None:
        tx = _tx(amount=Decimal("10.00"))
        rule = _rule(field="amount", operator="unknown_op", value="10")
        assert match_transaction(tx, [rule]) is None

    def test_invalid_amount_value_returns_none(self) -> None:
        tx = _tx(amount=Decimal("10.00"))
        rule = _rule(field="amount", operator="gt", value="not_a_number")
        assert match_transaction(tx, [rule]) is None

    def test_unknown_field_returns_none(self) -> None:
        tx = _tx(payee="REWE")
        rule = _rule(field="unknown_field", operator="contains", value="rewe")
        assert match_transaction(tx, [rule]) is None
