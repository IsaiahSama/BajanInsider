import React from "react";
import "./Entry.css";

const Entry = ({ title, summary, source, link, date }) => {
  return (
    <div className="Entry">
      <h2 className="Entry_title">{title}</h2>
      <p className="Entry_summary">{summary}</p>
      <div className="Entry_footerContainer">
        <p>{source}</p>
        <p>Posted on: {date}</p>
        <p>
          {" "}
          <a href={link} className="Entry_link">
            Read more...
          </a>
        </p>
      </div>
    </div>
  );
};

export default Entry;
