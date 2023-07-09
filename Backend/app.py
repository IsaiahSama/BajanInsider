# This is where the main Flask Backend will live

from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello_world():
    return "<p>Hello Readers!</p>"