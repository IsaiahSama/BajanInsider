# This is where the main Flask Backend will live

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import sqlalchemy as sql

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///BBNews.db"

db : sql = SQLAlchemy()
db.init_app(app)

# Models
class Entry(db.Model):
    """Class representing a New Entry"""
    id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String, nullable=False)
    source = db.Column(db.String, nullable=False)
    title = db.Column(db.String, nullable=False, unique=True)
    summary = db.Column(db.String, nullable=False)

    def get_as_dict(self):
        """Returns the entry as a dictionary for API reasons.
        
        Returns:
            dict"""
        
        return {
            "id": self.id,
            "link": self.link,
            "source": self.source,
            "title": self.title,
            "summary": self.summary
        }


# Creating the database
with app.app_context():
    db.create_all()

# Routing

@app.route("/")
def hello_world():
    return "<p>Hello Readers!</p>"

## Database Routing
@app.route('/add/entry/', methods=["POST"])
def add_entry():
    form = request.form
    
    entry = Entry(
        link=form['LINK'],
        source=form["SOURCE"],
        title=form["TITLE"],
        summary=form["SUMMARY"]
    )

    db.session.add(entry)
    db.session.commit()

    return "Pretty sure all went well"
    
@app.route("/get/entries/all/", methods=["POST"])
def get_all_entries():
    entries = db.session.execute(db.select(Entry)).fetchall()
    data = [entry[0].get_as_dict() for entry in entries]

    return data