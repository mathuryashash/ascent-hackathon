const express = require('express');
const app = express();
const port = 3000;

app.get('/', (req, res) => {
  res.send('<h1>Project Chimera Gateway</h1><p>System is online.</p>');
});

app.listen(port, () => {
  console.log(`Gateway UI listening at http://localhost:${port}`);
});
