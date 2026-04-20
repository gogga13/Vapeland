from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', views.home, name='home'),
    path('catalog/', views.catalog_page, name='catalog_page'),
    path('search/', views.search_products, name='search_products'),
    path('discounts/', views.discounts_page, name='discounts'),
    path('age-restrictions/', views.age_restrictions_page, name='age_restrictions'),
    path('responsible-consumption/', views.responsible_consumption_page, name='responsible_consumption'),
    path('api/np/cities/', views.search_np_cities, name='search_np_cities'),
    path('api/np/warehouses/', views.search_np_warehouses, name='search_np_warehouses'),
    path('password-reset/', views.password_reset_request_view, name='password_reset_request'),
    path('password-reset/confirm/', views.password_reset_confirm_view, name='password_reset_confirm'),
    path('profile/', views.profile, name='profile'),
    path('orders/', views.orders_page, name='orders_page'),
    path('api/orders/<int:order_id>/', views.order_api_detail, name='order_api_detail'),
    path('verify/', views.verify_page, name='verify_page'),
    path('cart/', views.cart_detail, name='cart_detail'),
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/', views.cart_update, name='cart_update'),
    path('cart/remove/', views.cart_remove, name='cart_remove'),
    path('cart/clear/', views.cart_clear, name='cart_clear'),
    path('checkout/', views.checkout, name='checkout'),
    path('place-order/', views.place_order, name='place_order'),
    path('product/<int:pk>/', views.product_detail_legacy, name='product_detail_legacy'),
    path('product/<str:slug>/', views.product_detail, name='product_detail'),
    path('product/<str:slug>/review/', views.add_product_review, name='add_product_review'),
    path('reviews/site/', views.add_site_review, name='add_site_review'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


