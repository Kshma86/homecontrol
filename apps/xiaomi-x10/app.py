from flask import Flask, render_template, send_from_directory

import config
from xiaomi_x10_api import (
    xiaomi_x10_bp,
    start_xiaomi_x10_mqtt
)

app = Flask(__name__)

app.register_blueprint(xiaomi_x10_bp)

start_xiaomi_x10_mqtt()


@app.route("/")
def index():
    return """
    <h1>HomeControl</h1>
    <ul>
        <li><a href="/xiaomi_x10">Xiaomi X10</a></li>
    </ul>
    """


@app.route("/xiaomi_x10")
def xiaomi_x10_page():
    return render_template("xiaomi_x10.html")


@app.route("/x10_maps/<path:filename>")
def xiaomi_x10_maps(filename):
    return send_from_directory(config.MAP_OUTPUT_DIR, filename)


if __name__ == "__main__":
    app.run(
        host=config.APP_HOST,
        port=config.APP_PORT,
        debug=config.APP_DEBUG
    )
