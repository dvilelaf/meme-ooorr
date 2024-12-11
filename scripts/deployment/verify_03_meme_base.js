const fs = require("fs");
const globalsFile = "globals.json";
let dataFromJSON = fs.readFileSync(globalsFile, "utf8");
const parsedData = JSON.parse(dataFromJSON);

const redemptionsFile = "scripts/deployment/memebase_campaign.json";
dataFromJSON = fs.readFileSync(redemptionsFile, "utf8");
const redemptionsData = JSON.parse(dataFromJSON);

const accounts = new Array();
const amounts = new Array();
for (let i = 0; i < redemptionsData.length; i++) {
    accounts.push(redemptionsData[i]["hearter"]);
    amounts.push(redemptionsData[i]["amount"].toString());
}

module.exports = [
    parsedData.olasAddress,
    parsedData.wethAddress,
    parsedData.uniV3positionManagerAddress,
    parsedData.buyBackBurnerProxyAddress,
    parsedData.minNativeTokenValue,
    accounts,
    amounts
];