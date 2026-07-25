from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from ..models import ItemAllocation, Person


@dataclass(frozen=True)
class AllocationShare:
    person: Person
    weight: Decimal = Decimal("1")

    @property
    def person_id(self):
        return self.person.id


def split_item_allocations(item, fallback_people=None):
    allocations = list(item.allocations.all())
    if not allocations:
        people = (
            fallback_people
            if fallback_people is not None
            else Person.objects.filter(active=True, is_deleted=False)
        )
        allocations = [AllocationShare(person=person) for person in people]
    cents = ItemAllocation.split_cents(item.total_price_cents, allocations)
    return list(zip(allocations, cents, strict=True))


def exact_item_allocations(item, fallback_people=None):
    allocations = list(item.allocations.all())
    if not allocations:
        people = (
            fallback_people
            if fallback_people is not None
            else Person.objects.filter(active=True, is_deleted=False)
        )
        allocations = [AllocationShare(person=person) for person in people]
    if not allocations:
        return []

    weights = [Decimal(str(allocation.weight)) for allocation in allocations]
    weight_sum = sum(weights, Decimal("0"))
    if item.total_price_cents == 0 or weight_sum <= 0:
        return [(allocation, Decimal("0")) for allocation in allocations]

    return [
        (allocation, Decimal(item.total_price_cents) * weight / weight_sum)
        for allocation, weight in zip(allocations, weights, strict=True)
    ]


def round_exact_cents(values_by_key):
    rounded = {
        key: int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        for key, value in values_by_key.items()
    }
    target_total = int(
        sum(values_by_key.values(), Decimal("0")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    difference = target_total - sum(rounded.values())
    if not difference:
        return rounded

    remainders = [
        (key, values_by_key[key] - Decimal(rounded[key]))
        for key in values_by_key
    ]
    remainders.sort(key=lambda pair: pair[1], reverse=difference > 0)
    step = 1 if difference > 0 else -1
    for key, _remainder in remainders[: abs(difference)]:
        rounded[key] += step
    return rounded
