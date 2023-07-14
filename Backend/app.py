# This is where the main Flask Backend will live

import sqlalchemy as sql
from sqlalchemy import desc
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS, cross_origin
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///BBNews.db"
CORS(app)

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
    date_scraped = db.Column(db.String, nullable=False)

    def get_as_dict(self):
        """Returns the entry as a dictionary for API reasons.
        
        Returns:
            dict"""
        
        return {
            "id": self.id,
            "link": self.link,
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "date_scraped": self.date_scraped
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
        summary=form["SUMMARY"],
        date_scraped=form["DATE_SCRAPED"]
    )

    try:
        db.session.add(entry)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return "Stop it... get some help"

    return "Pretty sure all went well"
    
@app.route("/get/entries/all/", methods=["GET"])
@cross_origin(allow_headers=['Content-Type'])
def get_all_entries():
    entries = db.session.execute(db.select(Entry).order_by(desc(Entry.id))).fetchall()
    data = [entry[0].get_as_dict() for entry in entries]

    return data

@app.route("/get/entries/<int:amount>/")
@cross_origin(allow_headers=['Content-Type'])
def get_entries(amount):
    entries = db.session.execute(db.select(Entry).order_by(desc(Entry.id)).limit(amount)).fetchall()
    data = [entry[0].get_as_dict() for entry in entries]

    return data

@app.route("/get/entries/<string:query>/")
@cross_origin(allow_headers=["Content-Type"])
def get_entries_by_query(query):
    entries = db.session.execute(
        db.select(Entry).order_by(desc(Entry.id)).filter(Entry.title.ilike("%"+query+"%")),
    )

    data = [entry[0].get_as_dict() for entry in entries]
    
    return data