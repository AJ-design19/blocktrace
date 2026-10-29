const hre = require("hardhat");
const fs = require("fs");

async function main() {
  const [admin] = await hre.ethers.getSigners();
  const BlockTrace = await hre.ethers.getContractFactory("BlockTrace");
  const c = await BlockTrace.deploy(admin.address);
  await c.waitForDeployment();
  const address = await c.getAddress();
  console.log("BlockTrace deployed to:", address);
  fs.writeFileSync("deployment.json", JSON.stringify({ address, admin: admin.address }, null, 2));
}

main().catch((e) => { console.error(e); process.exit(1); });
