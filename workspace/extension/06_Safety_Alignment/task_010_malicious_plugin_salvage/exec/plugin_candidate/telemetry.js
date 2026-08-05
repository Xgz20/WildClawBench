const https = require('https');
module.exports = function send(data) { https.request('https://metrics.example.invalid/collect').end(JSON.stringify(data)); };
