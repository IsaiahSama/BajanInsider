# This file will control access to the database.

from sqlite3 import connect

class Database:
    """This class is responsible for managing access to the News Database."""
    def __init__(self, name="BBNews.db"):
        self.name = name
        self.setup()

    def setup(self):
        """This method is responsible for setting up the Table in the database"""
        with connect(self.name) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS NewsTable (
                Link TEXT NOT NULL,
                Source TEXT NOT NULL,
                Title TEXT UNIQUE NOT NULL,
                Summary TEXT NOT NULL
            )""")
            db.commit()

    def add_entry(self, entry:dict) -> None:
        """This method adds an entry to the database.
        
        Args:
            entry (dict): A dictionary containing the keys: LINK, SOURCE, TITLE and SUMMARY
            
        Returns:
            None"""
        
        with connect(self.name) as db:
            db.execute("INSERT OR REPLACE INTO NewsTable (Link, Source, Title, Summary) VALUES (?, ?, ?, ?)", (entry['LINK'], entry['SOURCE'], entry['TITLE'], entry['SUMMARY']))
            db.commit()

    def add_entries(self, entries:dict) -> None:
        """This method adds several entries to the database.
        
        Args:
            entries (dict): A dictionary containing dictionaries containing the keys: LINK, SOURCE, TITLE and SUMMARY.
            
        Returns:
            None"""
        
        with connect(self.name) as db:
            for entry in entries.values():
                db.execute("INSERT OR REPLACE INTO NewsTable (Link, Source, Title, Summary) VALUES (?, ?, ?, ?)", (entry['LINK'], entry['SOURCE'], entry['TITLE'], entry['SUMMARY']))
            db.commit()

    def get_all_entries(self) -> list:
        """Returns all entries from the database
        
        Args:
            None 
            
        Returns:
            entries (list): A list of entries from the database."""
        
        with connect(self.name) as db:
            cursor = db.execute("SELECT * FROM NewsTable")
            rows = cursor.fetchall()

        return rows
    
    def get_entries_by(self, value:str, filter_:str('Source', 'Title')="Source") -> tuple:
        """Used to get entries either by Source or Title
        
        Args:
            value (str): Either the name of the Source or Title of the entry.
            filter (str): Either Source or Title. Determines which column to look under.
            
        Returns:
            entries (list | None): The entries matching the filter and value."""
        
        if filter_.title() not in ["Source", "Title"]:
            raise ValueError(f"{filter_} must be 'Source' or 'Title'")
        
        with connect(self.name) as db:
            cursor = db.execute("SELECT * FROM NewsTable WHERE ? like %?%", (filter_.title(), value))
            rows = cursor.fetchall()

        return rows