const fs = require("fs");
const globalsFile = "globals.json";
const dataFromJSON = fs.readFileSync(globalsFile, "utf8");
const parsedData = JSON.parse(dataFromJSON);
const buyBackBurnerAddress = parsedData.buyBackBurnerAddress;
const proxyData = "0x8129fc1c"; // initialize()

module.exports = [
    buyBackBurnerAddress,
    proxyData
];