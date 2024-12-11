// npx hardhat verify --constructor-args scripts/deployment/verify_04_meme_token.js TOKEN_ADDRESS --network NETWORK
const fs = require("fs");
const globalsFile = "globals.json";
const dataFromJSON = fs.readFileSync(globalsFile, "utf8");
const parsedData = JSON.parse(dataFromJSON);

module.exports = [
    parsedData.name,
    parsedData.symbol,
    parsedData.decimals,
    parsedData.totalSupply
];