from django.contrib import admin

from .models import Category, ItemAllocation, Person, Receipt, ReceiptItem


class ItemAllocationInline(admin.TabularInline):
    model = ItemAllocation
    extra = 0


class ReceiptItemInline(admin.TabularInline):
    model = ReceiptItem
    extra = 0


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "is_deleted")
    list_filter = ("active", "is_deleted")
    search_fields = ("name",)


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ("date", "market", "buyer", "created_at")
    list_filter = ("market", "buyer")
    search_fields = ("market",)
    inlines = [ReceiptItemInline]


@admin.register(ReceiptItem)
class ReceiptItemAdmin(admin.ModelAdmin):
    list_display = ("article", "receipt", "quantity", "total_price_cents")
    search_fields = ("article",)
    inlines = [ItemAllocationInline]


@admin.register(ItemAllocation)
class ItemAllocationAdmin(admin.ModelAdmin):
    list_display = ("item", "person", "weight")
    list_filter = ("person",)


admin.site.register(Category)
