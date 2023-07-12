import "./App.css";
import Entry from "./Entry";
import Header from "./Header";

import { useEffect, useState } from "react";

function App() {
  const [entries, setEntries] = useState([]);
  const flaskURL = "http://127.0.0.1:5000";

  useEffect(() => {
    const dataFetch = async () => {
      const data = await (await fetch(flaskURL + "/get/entries/15")).json();
      // const data = await (await fetch("url")).json();
      setEntries(data);
    };
    dataFetch();
  }, []);

  return (
    <div className="App">
      <Header />
      <hr />
      <div className="App_entries">
        {entries.map((entry) => (
          <Entry
            key={entry.id}
            title={entry.title}
            summary={entry.summary}
            source={entry.source}
            link={entry.link}
            date={entry.date_scraped}
          />
        ))}
      </div>
    </div>
  );
}

export default App;
