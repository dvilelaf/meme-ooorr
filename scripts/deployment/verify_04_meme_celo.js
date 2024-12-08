const fs = require("fs");
const globalsFile = "globals.json";
const dataFromJSON = fs.readFileSync(globalsFile, "utf8");
const parsedData = JSON.parse(dataFromJSON);

const factoryParams = {
    parsedData.olasAddress,
    parsedData.celoAddress,
    parsedData.uniV3positionManagerAddress,
    parsedData.buyBackBurnerAddress,
    parsedData.minNativeTokenValue,
}

module.exports = [
    factoryParams,
    parsedData.l2TokenBridgeAddress
];