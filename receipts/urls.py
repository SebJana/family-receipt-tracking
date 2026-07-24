from django.urls import path

from . import views


app_name = "receipts"

urlpatterns = [
    path("", views.receipt_list, name="receipt_list"),
    path("receipts/new/", views.receipt_create, name="receipt_create"),
    path("receipts/<int:receipt_id>/items/", views.receipt_items, name="receipt_items"),
    path("receipts/<int:receipt_id>/edit/", views.receipt_edit, name="receipt_edit"),
    path("receipts/<int:receipt_id>/delete/", views.receipt_delete, name="receipt_delete"),
    path("import/", views.import_receipts, name="import"),
    path("stats/", views.stats, name="stats"),
    path("people/", views.people, name="people"),
    path("categories/", views.categories, name="categories"),
    path("health/", views.health, name="health"),
]
