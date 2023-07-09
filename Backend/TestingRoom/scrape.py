from requests import get
from bs4 import BeautifulSoup

URL = "https://www.google.com/search?client=opera-gx&hs=boG&sxsrf=AB5stBin05pDbY87etcAQJXd0ANb4Cme2Q:1688919970786&q=Latest+AND+Barbados+AND+news&tbm=nws&sa=X&ved=2ahUKEwjwmKaXhYKAAxVMhIQIHbH1DOgQ0pQJegQIEhAB&biw=1126&bih=599&dpr=1.65"

page = get(URL)
page.raise_for_status()
soup = BeautifulSoup(page.text, "html.parser")

with open('test.html', "w") as fp:
    fp.write(page.text)