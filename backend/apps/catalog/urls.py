from django.urls import path

from .views import CategoryListView, ProductDetailView, ProductListView, ProductReviewListView

urlpatterns = [
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("products/", ProductListView.as_view(), name="product-list"),
    path("products/<slug:slug>/", ProductDetailView.as_view(), name="product-detail"),
    path("products/<slug:slug>/reviews/", ProductReviewListView.as_view(), name="product-reviews"),
]
