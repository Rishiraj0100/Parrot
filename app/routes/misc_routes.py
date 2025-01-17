from __future__ import annotations

import logging
from datetime import timedelta

from quart import Response, jsonify, request
from quart_rate_limiter import rate_limit

from utilities.converters import convert_bool

from ..quart_app import app, ipc

log = logging.getLogger("api")


@app.route("/")
@rate_limit(limit=5, period=timedelta(seconds=1))
async def index() -> Response:
    return jsonify({"status": "running"})


@app.route("/echo/<msg>", methods=["GET", "POST"])
async def echo(msg: str) -> Response:
    get_raw_data = dict(request.args)
    return jsonify({"status": "running", "message": msg, "GET": get_raw_data, "POST": await request.get_json()})


@app.route("/get/guilds")
async def get_guilds() -> Response:
    ipc_response = await ipc.request("guilds")
    if not ipc_response:
        return jsonify({"status": "error", "message": "No guilds found"})
    return jsonify({"status": "success", **ipc_response.response})  # type: ignore


@app.route("/routes")
async def routes() -> Response:
    rules = app.url_map.iter_rules()

    ls = [{"methods": list(rule.methods) if rule.methods else [], "path": str(rule)} for rule in rules]
    return jsonify({"status": "success", "routes": ls})


ERROR_CODES = [400, 401, 403, 404, 405, 429, 500, 501, 502, 503, 504]

for code in ERROR_CODES:

    @app.errorhandler(code)
    async def error_handler(e: Exception) -> Response:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/nsfw_links/<count>")
@rate_limit(limit=10, period=timedelta(seconds=1))
async def nsfw_links(count: str) -> Response:
    if count.isdigit():
        count = int(count)
    else:
        return jsonify({"status": "error", "message": "Invalid count"})

    tp = request.args.get("type", None)
    gif = request.args.get("gif", None)
    gif = convert_bool(gif) if gif else True
    ipc_response = await ipc.request("nsfw_links", count=int(count), type=tp, gif=gif)
    if not ipc_response:
        return jsonify({"status": "error", "message": "No guilds found"})

    return jsonify({"status": "success", **ipc_response.response})
