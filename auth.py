# -*- coding: utf-8 -*-
"""登录鉴权模块"""
from functools import wraps

from flask import jsonify, redirect, request, session

import database as db


def current_user():
    return session.get("user")


def check_login(username, password):
    user = db.get_user_by_login(username)
    if user and db.verify_password(password, user["password_hash"]):
        return user
    return None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "登录已过期，请重新登录"}), 401
            return redirect("/login")
        return view(*args, **kwargs)

    return wrapper
