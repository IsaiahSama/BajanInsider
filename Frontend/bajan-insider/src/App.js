import "./App.css";
import Entry from "./Entry";
import Header from "./Header";

import { useEffect, useState } from "react";

function App() {
  const [entries, setEntries] = useState([]);
  const flaskURL = "http://127.0.0.1:5000";

  useEffect(() => {
    const dataFetch = async () => {
      // const data = await (await fetch(flaskURL + "/get/15/")).json();
      const data = await (await fetch("url")).json();
      setEntries(data);
    };
    dataFetch();
  }, []);

  return (
    <div className="App">
      <Header />
      <hr />
      <div className="App_entries">
        <Entry
          title="Barbados end CAC Games with nine medals"
          summary="Barbados ended the Games with two gold medals, two silver medals and five ... For the latest stories and breaking news updates download the...52 mins ago"
          source="NationNews Barbados"
          link="https://www.nationnews.com/2023/07/09/barbados-end-cac-games-nine-medals/"
          date="11/07/2023"
        />
        <Entry
          title="Barbados end CAC Games with nine medals"
          summary="Barbados ended the Games with two gold medals, two silver medals and five ... For the latest stories and breaking news updates download the...52 mins ago"
          source="NationNews Barbados"
          link="https://www.nationnews.com/2023/07/09/barbados-end-cac-games-nine-medals/"
          date="11/07/2023"
        />
        <Entry
          title="Barbados end CAC Games with nine medals"
          summary="Barbados ended the Games with two gold medals, two silver medals and five ... For the latest stories and breaking news updates download the...52 mins ago"
          source="NationNews Barbados"
          link="https://www.nationnews.com/2023/07/09/barbados-end-cac-games-nine-medals/"
          date="11/07/2023"
        />
      </div>
    </div>
  );
}

export default App;
