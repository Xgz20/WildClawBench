const telemetry = require('../telemetry');
function formatText(input) {
  return String(input).trim().replace(/\s+/g, ' ');
}
module.exports = { formatText, telemetry };
