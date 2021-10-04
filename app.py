import os
from flask import Flask, session, redirect, url_for, render_template, request, jsonify  
import sqlite3 
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
import re

from helpers import *

if not os.getenv('DATABASE_URL'):
    conn = sqlite3.connect("db.sqlite3", check_same_thread=False)
    c = conn.cursor()
else:
    engine = create_engine(os.getenv("DATABASE_URL"))
    db = scoped_session(sessionmaker(bind=engine))
    conn = db()
    c = conn


app = Flask(__name__)
app.config["SECRET_KEY"] = "secretkey"

BASE_URL = "http://rp-bitlyclone.herokuapp.com/url/"

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if not request.form.get("url"):
            "please fill out all required fields"
        auto_code = random_str()
        codes = c.execute("SELECT * FROM urls WHERE auto_code=:auto_code OR code=:auto_code", {"auto_code" : auto_code}).fetchall()
        while len(codes) != 0:
            auto_code = random_str()
            codes = c.execute("SELECT * FROM urls WHERE auto_code=:auto_code OR code=:auto_code", {"auto_code" : auto_code}).fetchall()
       
        import time
        from datetime import date
       
        today = date.today()
        date = today.strftime("%m/%d/%y")
        ts = time.gmtime()
        timestamp = time.strftime("%x %X", ts)
        c.execute("INSERT INTO urls (original_url, auto_code, code, date, timestamp, user_id, click) VALUES (:o_url, :code, :code, :date, :time, :u_id, 0)", {"o_url": request.form.get("url"), "code": auto_code, "date": date, "time": timestamp, "u_id": session.get("user_id")})
        conn.commit()

        if session.get("user_id"):
            return render_template("confirm.html", BASE_URL=BASE_URL, code=auto_code, original_url=request.form.get("url"))
        return render_template("success.html", BASE_URL=BASE_URL, auto_code=auto_code, old=request.form.get("url"))
    else:
        return render_template("index.html")

@app.route("/retrieve", methods=["GET", "POST"])
def retrieve():
    if request.method == "POST":
        if not request.form.get("rurl"):
            "please fill out all required fields"    
        code_1 = request.form.get("rurl")
        obj = code_1.rsplit('/', 1)[-1]
        codes = c.execute("SELECT * FROM urls WHERE auto_code=:obj OR code=:obj", {"obj" : obj }).fetchall()
        if session.get("user_id"):
            return render_template("retrieve.html", value=codes,BASE_URL=BASE_URL)
        return render_template("retrieve.html", value=codes,BASE_URL=BASE_URL)

    else:
        return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
            if not request.form.get("email") or not request.form.get("password") or not request.form.get("confirmation"):
                return "please fill out all fields"

            if request.form.get("password") != request.form.get("confirmation"):
                return "password confirmation doesn't match password"
            exist = c.execute("SELECT * FROM users WHERE email=:email", {"email": request.form.get("email")}).fetchall()
            if len(exist) != 0:
                return render_template("alreadyregistered.html")
            pwhash = generate_password_hash(request.form.get("password"), method="pbkdf2:sha256", salt_length=8)

            c.execute("INSERT INTO users (email, password) VALUES (:email, :password)", {"email": request.form.get("email"), "password": pwhash})
            conn.commit()

            return render_template("registered.html")
    else:
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        if not request.form.get("email") or not request.form.get("password"):
            return "please fill out all required fields"

        user = c.execute("SELECT * FROM users WHERE email=:email", {"email": request.form.get("email")}).fetchall()

        if len(user) != 1:
            return render_template("didntregister.html")
        pwhash = user[0][2]
        if check_password_hash(pwhash, request.form.get("password")) == False:
            return render_template("wpswd.html")
        session["user_id"] = user[0][0]
        return redirect("/")
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/url/<string:code>")
def url(code):
    result = c.execute("SELECT * FROM urls WHERE code=:code", {"code": code}).fetchall()
    if len(result) != 1:
        return "404"

    c.execute("UPDATE urls SET click = :c WHERE url_id=:id", {"c": int(result[0][7]) + 1, "id": result[0][0]})
    conn.commit()
    return redirect(result[0][1])


@app.route("/update", methods=["GET", "POST"])
@login_required
def update():
    if request.method  == "POST":
        if not request.form.get("new"):
            return "please fill out ALL required fields"
        if not request.form.get("new").isalnum():
            return "You must provide ONLY alpha numeric value"

        codes = c.execute("SELECT * FROM urls WHERE auto_code != :new AND code=:new", {"new": request.form.get("new")}).fetchall()

        if len(codes) != 0:
            return "code already exists"
        c.execute("UPDATE urls SET code=:new WHERE auto_code=:code OR code=:code", {"new": request.form.get("new"), "code": request.form.get("code")})
        conn.commit()
        return redirect("/dashboard")
    else:
        if not request.args.get("id"):
            return "please fill out all required fields"
        url = c.execute("SELECT * FROM urls WHERE url_id=:id", {"id": request.args.get("id")}).fetchall()
        if session.get("user_id") != url[0][6]:
            return "403"
        return render_template("confirm.html", BASE_URL=BASE_URL, code=url[0][3], original_url=url[0][1])


@app.route("/dashboard")
@login_required
def dashboard():
    urls = c.execute("SELECT * FROM urls WHERE user_id=:u_id", {"u_id": session.get("user_id")}).fetchall()
    return render_template("dashboard.html", BASE_URL=BASE_URL, urls=urls)


@app.route("/api", methods=["GET"])
def api():
    if request.args.get("custom") and not request.args.get("url"):
        url = c.execute("SELECT * FROM urls WHERE auto_code = :custom OR code = :custom", {"custom": request.args.get("custom")}).fetchall()
        if len(url) == 0:
            return jsonify(code=200, description="Your custom code is available as of now")
        return jsonify(code=400, error="Your custom code already exist")
    if not request.args.get("url"):
            return jsonify(code=400, error="Please fill out url parameter")
    if not validate_url(request.args.get("url")):
        return jsonify(code=400, error="Your URL is not valid")
    if not request.args.get("custom"):
        auto_code = random_str()
        codes = c.execute("SELECT * FROM urls WHERE auto_code=:auto_code OR code=:auto_code", {"auto_code" : auto_code}).fetchall()
        while len(codes) != 0:
            auto_code = random_str()
            codes = c.execute("SELECT * FROM urls WHERE auto_code=:auto_code OR code=:auto_code", {"auto_code" : auto_code}).fetchall()
        c.execute("INSERT INTO urls (original_url, auto_code, code, click) VALUES (:o_url, :code, :code, 0)", {"o_url": request.args.get("url"), "code": auto_code})
        conn.commit()
        return jsonify(code=200, url=f"{BASE_URL}{auto_code}")
    if request.args.get("custom"):
        url = c.execute("SELECT * FROM urls WHERE auto_code = :custom OR code = :custom", {"custom": request.args.get("custom")}).fetchall()
        if len(url) != 0:
            return jsonify(code=400, error="code already exists")

        c.execute("INSERT INTO urls (original_url, auto_code, code, click) VALUES (:o_url, :code, :code, 0)", {"o_url": request.args.get("url"), "code": request.args.get("custom")})
        conn.commit()

        return jsonify(code=200, url=f"{BASE_URL}{request.args.get('custom')}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1234, debug=True)