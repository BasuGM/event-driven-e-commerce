from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination


class StrictPageNumberPagination(PageNumberPagination):
    """Page-number pagination that rejects malformed params with 400 instead of guessing.

    DRF's default silently ignores a bad ``page_size`` and turns ``page=abc`` into a 404; we
    want clients to hear about their mistake. A *valid* page past the end still 404s.
    """

    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        errors = {}
        for param, upper in ((self.page_query_param, None), (self.page_size_query_param, self.max_page_size)):
            raw = request.query_params.get(param)
            if raw is None or (param == self.page_query_param and raw == "last"):
                continue
            if not raw.isdigit() or int(raw) < 1:
                errors[param] = ["Must be a positive integer."]
            elif upper is not None and int(raw) > upper:
                errors[param] = [f"Must be at most {upper}."]
        if errors:
            raise ValidationError(errors)
        return super().paginate_queryset(queryset, request, view)


class ReviewPagination(StrictPageNumberPagination):
    page_size = 10
    max_page_size = 50
