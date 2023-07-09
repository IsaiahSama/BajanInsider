# This is where the main Flask Backend will live

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import sqlalchemy as sql

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///BBNews.db"

db : sql = SQLAlchemy()
db.init_app(app)

# Models
class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String, nullable=False)
    source = db.Column(db.String, nullable=False)
    title = db.Column(db.String, nullable=False, unique=True)
    summary = db.Column(db.String, nullable=False)

# Creating the data
with app.app_context():
    db.create_all()

# Routing

@app.route("/")
def hello_world():
    return "<p>Hello Readers!</p>"