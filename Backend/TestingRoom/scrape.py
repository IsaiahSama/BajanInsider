from requests import get
from bs4 import BeautifulSoup
from pprint import pprint

URL = "https://www.google.com/search?client=opera-gx&hs=boG&sxsrf=AB5stBin05pDbY87etcAQJXd0ANb4Cme2Q:1688919970786&q=Latest+AND+Barbados+AND+news&tbm=nws&sa=X&ved=2ahUKEwjwmKaXhYKAAxVMhIQIHbH1DOgQ0pQJegQIEhAB&biw=1126&bih=599&dpr=1.65"

page = get(URL)
page.raise_for_status()
soup = BeautifulSoup(page.text, "html.parser")

with open('test.html', "w") as fp:
    fp.write(page.text)

# Parsing time
link_selector = "#main > div:nth-child({}) > div > a"
source_selector = "#main > div:nth-child({}) > div > a > div.egMi0.kCrYT > div > div.sCuL3 > div"
title_selector = "#main > div:nth-child({}) > div > a > div.egMi0.kCrYT > div > div.j039Wc > h3 > div"
summary_selector = "#main > div:nth-child({}) > div > a > div:nth-child(2) > div:nth-child(2) > div > div > div"

links, sources, titles, summaries = [[] for _ in range(4)]

for i in range(4, 14):
    links.append(soup.css.select_one(link_selector.format(i)).get("href").split("?q=")[1].split("&sa")[0])
    sources.append(soup.css.select_one(source_selector.format(i)).text)
    titles.append(soup.css.select_one(title_selector.format(i)).text)
    summaries.append(soup.css.select_one(summary_selector.format(i)).text)

# Aggregation time
# entries = dict(zip(titles, summaries))
pprint(links[:3], indent=4)
print("-"*50)
pprint(sources[:3], indent=4)
print("-"*50)
pprint(titles[:3], indent=4)
print("-"*50)
pprint(summaries[:3], indent=4)