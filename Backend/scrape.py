# This file will be responsible for the scraping of the news
from requests import get
from bs4 import BeautifulSoup
from Database import Database

# Pre Setup
URL = "https://www.google.com/search?client=opera-gx&hs=boG&sxsrf=AB5stBin05pDbY87etcAQJXd0ANb4Cme2Q:1688919970786&q=Latest+AND+Barbados+AND+news&tbm=nws&sa=X&ved=2ahUKEwjwmKaXhYKAAxVMhIQIHbH1DOgQ0pQJegQIEhAB&biw=1126&bih=599&dpr=1.65"

# Functions

def get_soup() -> BeautifulSoup:
    """Retrieves the Beautiful Soup from the webpage.
    
    Args:
        None
        
    Returns: 
        BeautifulSoup -> The Soup object"""
    
    page = get(URL)
    page.raise_for_status()
    
    return BeautifulSoup(page.text, "html.parser")

def get_entries(soup: BeautifulSoup) -> dict:
    """Gets the first 10 entries from the given soup object.
    
    Args:
        soup (BeautifulSoup): The parsed webpage
        
    Returns:
        entries (dict): A dictionary of dictionaries for each entry."""
    
    # Meta Information
    start_index = 4
    link_selector = "#main > div:nth-child({}) > div > a"
    source_selector = "#main > div:nth-child({}) > div > a > div.egMi0.kCrYT > div > div.sCuL3 > div"
    title_selector = "#main > div:nth-child({}) > div > a > div.egMi0.kCrYT > div > div.j039Wc > h3 > div"
    summary_selector = "#main > div:nth-child({}) > div > a > div:nth-child(2) > div:nth-child(2) > div > div > div"

    # Filtering out the data.
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

    return entries

def main():
    # Get the soup
    soup = get_soup()

    # Get the 10 latest Entries
    entries = get_entries(soup)

    # Insert Entries into the database
    db = Database()
    db.add_entries(entries)


if __name__ == "__main__":
    main()