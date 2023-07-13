import "./App.css";
import Entries from "./Entries";
import Header from "./Header";

function App() {
  return (
    <div className="App">
      <Header />
      <hr />
      <div className="App_entries">
        <Entries />
      </div>
    </div>
  );
}

export default App;
