import React from "react";
import "./Entry.css";

const Entry = ({ title, summary, source, link, date }) => {
  return (
    <div className="Entry container card is-fluid">
      <h2 className="Entry_title card-header-title">{title}</h2>
      <p className="Entry_summary card-content">{summary}</p>
      <div className="Entry_footerContainer card-footer">
        <p className="card-footer-item">{source}</p>
        <p className="card-footer-item">Scraped on: {date}</p>
        <p className="card-footer-item">
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
