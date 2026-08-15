import os

from flask import Flask, send_from_directory


def create_app():
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    app = Flask(__name__, static_folder=static_dir, static_url_path="")

    from app.routes.events import events_bp
    from app.routes.vehicles import vehicles_bp
    from app.routes.audit import audit_bp
    from app.routes.replay import replay_bp

    app.register_blueprint(events_bp)
    app.register_blueprint(vehicles_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(replay_bp)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app
