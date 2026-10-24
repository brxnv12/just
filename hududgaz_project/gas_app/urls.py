from django.urls import path

from . import views

urlpatterns = [
    path("me/", views.MeView.as_view()),
    path("accounts/", views.AccountListCreate.as_view()),
    path("accounts/<int:pk>/", views.AccountDetail.as_view()),
    path("accounts/<int:pk>/dashboard/", views.DashboardView.as_view()),
    path("readings/", views.ReadingCreate.as_view()),
    path("topup/", views.TopupView.as_view()),
    path("appeals/", views.AppealListCreate.as_view()),
    path("chat/", views.ChatView.as_view()),
]
