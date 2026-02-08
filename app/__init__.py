from flask import Flask
from app.config import load_config
from app.db import connect, init_db
from app.web.routes import bp as web_bp

def create_app():
    cfg = load_config().raw

    app = Flask(__name__)
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)

    app.config["CFG"] = cfg
    app.config["DB"] = conn

    app.register_blueprint(web_bp)
    return app
