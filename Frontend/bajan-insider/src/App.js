import "./App.css";
import Entries from "./Entries";
import Header from "./Header";
import "bulma/css/bulma.min.css";

function App() {
  return (
    <div className="App container">
      <Header />
      <hr />
      <div className="App_entries">
        <Entries />
      </div>
    </div>
  );
}

export default App;
