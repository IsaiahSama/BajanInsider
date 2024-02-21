# This file will be responsible for the scraping of the news
from requests import get, post
from bs4 import BeautifulSoup
from datetime import datetime
from time import sleep

# Pre Setup
URL = "https://www.google.com/search?sxsrf=AB5stBjILCztpUnyME1oXKPd-e9nC_t3hQ:1689017615618&q=barbados+news&tbm=nws&sa=X&ved=2ahUKEwjw6f338ISAAxWxtDEKHVBwBjMQ0pQJegQIDBAB&cshid=1689017689554091&biw=1652&bih=412&dpr=1.1"
FLASK_APP_URL = "https://bajan-insider-service.vercel.app"
# FLASK_APP_URL = "http://127.0.0.1:5000"

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
            "SUMMARY":soup.css.select_one(summary_selector.format(index)).text,
            "DATE_SCRAPED": datetime.now().strftime("%d/%m/%Y")
        }
        
        entries[i] = entry 

    return entries

def add_entry(entry: dict) -> None:
    """Will send a request to the flask server to store the entry in the database.
    
    Args:
        entry (dict): A dictionary representing the scraped entry.
        
    Returns:
        None"""
    
    # print(entry)
    response = post(FLASK_APP_URL + "/add/entry/", data=entry)
    try:
        response.raise_for_status()
    except: 
        pass
    print(response.text)    

def update_entries():
    sleep(15) # Just long enough for the server to actually start
    # Get the soup
    soup = get_soup()

    # Get and add the Entries to the database.
    [add_entry(entry) for entry in get_entries(soup).values()]

if __name__ == "__main__":
    update_entries()