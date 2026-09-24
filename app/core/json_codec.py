"""Exact JSON numbers shared by persistence and HTTP responses (no float coercion)."""

from datetime import date, datetime

import simplejson
from starlette.responses import Response


def _default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported JSON type: {type(value).__name__}")


def dumps(value):
    return simplejson.dumps(value, use_decimal=True, ensure_ascii=False,
                            allow_nan=False, default=_default)


def loads(value):
    return simplejson.loads(value, use_decimal=True, allow_nan=False)


class ExactJSONResponse(Response):
    media_type = "application/json"

    def render(self, content):
        return dumps(content).encode("utf-8")
