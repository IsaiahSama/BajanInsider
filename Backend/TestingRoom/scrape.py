from requests import get
from bs4 import BeautifulSoup

URL = "https://www.google.com/search?client=opera-gx&hs=boG&sxsrf=AB5stBin05pDbY87etcAQJXd0ANb4Cme2Q:1688919970786&q=Latest+AND+Barbados+AND+news&tbm=nws&sa=X&ved=2ahUKEwjwmKaXhYKAAxVMhIQIHbH1DOgQ0pQJegQIEhAB&biw=1126&bih=599&dpr=1.65"

page = get(URL)
page.raise_for_status()
soup = BeautifulSoup(page.text, "html.parser")

with open('test.html', "w") as fp:
    fp.write(page.text)

# Parsing time
title_selector = "#main > div:nth-child({}) > div > a > div.egMi0.kCrYT > div > div.j039Wc > h3 > div"
summary_selector = "#main > div:nth-child({}) > div > a > div.egMi0.kCrYT > div > div.j039Wc > h3 > div"

#main > div:nth-child(4) > div > a > div.egMi0.kCrYT > div > div.j039Wc > h3 > div
#main > div:nth-child(5) > div > a > div.egMi0.kCrYT > div > div.j039Wc > h3 > div

titles, summaries = list(), list()
for i in range(4, 14):
    titles.append(soup.css.select(title_selector.format(i)))
    summaries.append(soup.css.select(summary_selector.format(i)))

print(titles[:5])
print(summaries[:2])