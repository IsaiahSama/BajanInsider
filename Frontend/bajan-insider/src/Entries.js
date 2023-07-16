import React, { useState, useEffect } from "react";
import "./Entries.css";
import Entry from "./Entry";

const Entries = () => {
  const [param, setParam] = useState("");
  const [entries, setEntries] = useState([]);

  const flaskURL = "http://127.0.0.1:5000";

  useEffect(() => {
    const dataFetch = async () => {
      const data = await (await fetch(flaskURL + "/get/entries/15")).json();
      //   const data = await (await fetch("url")).json();
      setEntries(data);
    };
    dataFetch();
  }, []);

  const modifyParam = (value) => {
    setParam(value);
    let term = value === "" ? "15" : value;
    const dataFetch = async () => {
      const data = await (
        await fetch(flaskURL + "/get/entries/" + term + "/")
      ).json();
      setEntries(data);
    };

    dataFetch();
  };

  return (
    <div className="Entries">
      <div className="Entries_searchBar level level-right">
        <p className="mr-2">Search bajan news here: </p>
        <input value={param} onChange={(e) => modifyParam(e.target.value)} />
      </div>
      <h1>Latest News:</h1>
      <div className="Entries_container container">
        {/* <Entry
          key={1}
          title="Barbados end CAC Games with nine medals"
          summary="Barbados ended the Games with two gold medals, two silver medals and five ... For the latest stories and breaking news updates download the...52 mins ago"
          source="NationNews Barbados"
          link="https://www.nationnews.com/2023/07/09/barbados-end-cac-games-nine-medals/"
          date="07/02/2021"
        />

        <Entry
          key={2}
          title="How Barbados Became a Leader in the Push for Reparations | Time"
          summary="Inside Barbados' Historic Push for Slavery Reparations ... A decade has happened for us within the last year or so.”...3 days ago"
          source="TIME"
          link="https://time.com/6290949/barbados-reparations/"
          date="07/04/2021"
        /> */}

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
};

export default Entries;
