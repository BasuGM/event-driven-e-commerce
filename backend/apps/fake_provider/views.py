from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.formatting import format_brl

from .models import FakeIntent
from .provider import FAIL, SUCCEED, SUCCEED_LATER, PaymentExpired, choose

DELAYS = [("10", "10 seconds"), ("60", "1 minute"), ("after_expiry", "After the stock hold expires")]


@require_http_methods(["GET", "POST"])
def hosted_page(request, intent_id: str):
    """The provider's hosted payment page (like Stripe Checkout). Dev/test only."""
    intent = get_object_or_404(FakeIntent, pk=intent_id)
    now = timezone.now()
    expired = intent.expires_at is not None and now >= intent.expires_at
    if request.method == "POST" and not expired and intent.status == FakeIntent.Status.REQUIRES_PAYMENT:
        choice = request.POST.get("choice")
        if choice in (SUCCEED, FAIL, SUCCEED_LATER):
            delay = 0.0
            if choice == SUCCEED_LATER:
                raw = request.POST.get("delay", "10")
                if raw == "after_expiry" and intent.expires_at:
                    delay = (intent.expires_at - now).total_seconds() + 30
                else:
                    delay = float(raw) if raw.isdigit() else 10.0
            try:
                choose(
                    intent, choice, delay=delay, now=now,
                    twice=request.POST.get("twice") == "on",
                    out_of_order=choice != FAIL and request.POST.get("out_of_order") == "on",
                )
            except PaymentExpired:
                expired = True
            else:
                return HttpResponseRedirect(intent.return_url)
    return render(
        request,
        "fake_provider/hosted_page.html",
        {
            "intent": intent,
            "amount": format_brl(intent.amount),
            "expired": expired,
            "delays": DELAYS,
            "twice_default": settings.FAKE_PROVIDER_DUPLICATE_DELIVERY,
        },
    )
