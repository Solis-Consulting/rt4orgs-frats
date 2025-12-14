const fs = require("fs");
const path = require("path");
const express = require("express");
const app = express();

app.use(express.json());
app.use(express.static(UI_DIR));

const CONTACTS_DIR = path.join(__dirname, "contacts");
const UI_DIR = path.join(__dirname, "..", "ui");

function loadAll() {
  const folders = fs.readdirSync(CONTACTS_DIR);
  const map = {};

  folders.forEach(folder => {
    const folderPath = path.join(CONTACTS_DIR, folder);
    const statePath = path.join(folderPath, "state.json");
    const msgPath = path.join(folderPath, "message.txt");

    if (!fs.existsSync(statePath)) return;

    const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
    const message = fs.existsSync(msgPath) ? fs.readFileSync(msgPath, "utf8") : "";

    const baseName = folder.split("_")[0];

    if (!map[baseName]) {
      map[baseName] = {
        name: baseName,
        folders: [],
        latest_state: null
      };
    }

    map[baseName].folders.push({
      folder,
      state,
      message
    });

    map[baseName].latest_state = state;
  });

  return map;
}

// Serve UI files from ui/ directory (handled by express.static above)
// Root route will serve index.html from ui/

app.get("/api/all", (req, res) => {
  res.json(loadAll());
});

// Legacy endpoint for backwards compatibility
app.get("/all", (req, res) => {
  res.json(loadAll());
});

app.get("/api/lead/:name", (req, res) => {
  const all = loadAll();
  const lead = all[req.params.name];
  if (!lead) return res.status(404).json({ error: "Not found" });
  res.json(lead);
});

// Legacy endpoint for backwards compatibility
app.get("/lead/:name", (req, res) => {
  const all = loadAll();
  const lead = all[req.params.name];
  if (!lead) return res.send("Not found");

  let html = "<html><body style='font-family:Arial;padding:20px'>";
  html += "<h2>" + lead.name + "</h2>";
  html += "<p>State: " + (lead.latest_state?.next_state || "unknown") + "</p>";

  lead.folders.forEach(f => {
    html += "<h3>Folder: " + f.folder + "</h3>";
    html += "<pre>" + JSON.stringify(f.state, null, 2) + "</pre>";
    html += "<h4>Message:</h4>";
    html += "<pre>" + f.message + "</pre>";
    html += "<hr>";
  });

  html += "</body></html>";
  res.send(html);
});

app.listen(3005, () => {
  console.log("Lead console running at http://localhost:3005");
});
