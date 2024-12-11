const fs = require("fs");
const globalsFile = "globals.json";
const dataFromJSON = fs.readFileSync(globalsFile, "utf8");
const parsedData = JSON.parse(dataFromJSON);
const memeFactoryAddress = parsedData.memeFactoryAddress;
const livenessRatio = parsedData.livenessRatio;

module.exports = [
    memeFactoryAddress,
    livenessRatio
];