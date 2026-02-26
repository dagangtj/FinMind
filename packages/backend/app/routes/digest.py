from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.weekly_digest import generate_weekly_digest
from ..services.cache import cache_get, cache_set
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


def _digest_cache_key(uid: int, year: int, week: int) -> str:
    return f"user:{uid}:weekly_digest:{year}-W{week:02d}"


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Return a smart weekly financial digest with trends and insights.

    Query params:
        year (int, optional): ISO year. Defaults to current.
        week (int, optional): ISO week number. Defaults to current.
    """
    uid = int(get_jwt_identity())

    today = date.today()
    iso = today.isocalendar()
    try:
        year = int(request.args.get("year", iso[0]))
        week = int(request.args.get("week", iso[1]))
    except (ValueError, TypeError):
        return jsonify(error="invalid year or week parameter"), 400

    if not (1 <= week <= 53):
        return jsonify(error="week must be between 1 and 53"), 400

    key = _digest_cache_key(uid, year, week)
    cached = cache_get(key)
    if cached:
        return jsonify(cached)

    digest = generate_weekly_digest(uid, year, week)

    # Cache for 10 minutes (current week) or 1 hour (past weeks)
    is_current = year == iso[0] and week == iso[1]
    ttl = 600 if is_current else 3600
    cache_set(key, digest, ttl_seconds=ttl)

    logger.info("Weekly digest served user=%s year=%s week=%s", uid, year, week)
    return jsonify(digest)
