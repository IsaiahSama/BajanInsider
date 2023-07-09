from requests import get
from bs4 import BeautifulSoup
from sqlite3 import connect
from os import remove, path
from pprint import pprint

URL = "https://www.google.com/search?client=opera-gx&hs=boG&sxsrf=AB5stBin05pDbY87etcAQJXd0ANb4Cme2Q:1688919970786&q=Latest+AND+Barbados+AND+news&tbm=nws&sa=X&ved=2ahUKEwjwmKaXhYKAAxVMhIQIHbH1DOgQ0pQJegQIEhAB&biw=1126&bih=599&dpr=1.65"

page = get(URL)
page.raise_for_status()
soup = BeautifulSoup(page.text, "html.parser")

with open('test.html', "w") as fp:
    fp.write(page.text)

# Parsing time
start_index = 4
link_selector = "#main > div:nth-child({}) > div > a"
source_selector = "#main > div:nth-child({}) > div > a > div.egMi0.kCrYT > div > div.sCuL3 > div"
title_selector = "#main > div:nth-child({}) > div > a > div.egMi0.kCrYT > div > div.j039Wc > h3 > div"
summary_selector = "#main > div:nth-child({}) > div > a > div:nth-child(2) > div:nth-child(2) > div > div > div"

# links, sources, titles, summaries = [[] for _ in range(4)]
entries = {}

for i in range(10):
    index = start_index + i
    entry = {
        "LINK": soup.css.select_one(link_selector.format(index)).get("href").split("?q=")[1].split("&sa")[0],
        "SOURCE": soup.css.select_one(source_selector.format(index)).text,
        "TITLE": soup.css.select_one(title_selector.format(index)).text,
        "SUMMARY":soup.css.select_one(summary_selector.format(index)).text
    }
    
    entries[i] = entry 

# Database Setup
if path.exists("testing.sqlite3"): remove("testing.sqlite3")
with connect("testing.sqlite3") as db:
    db.execute("CREATE TABLE TEST (link TEXT NOT NULL, source TEXT NOT NULL, title TEXT UNIQUE NOT NULL, summary TEXT NOT NULL)")
    db.commit()

# Database addition
with connect("testing.sqlite3") as db:
    for e in entries.values():
        db.execute("INSERT OR REPLACE INTO TEST (link, source, title, summary) VALUES (?, ?, ?, ?)", (e['LINK'], e['SOURCE'], e['TITLE'], e['SUMMARY']))
        db.commit()

print("Complete")