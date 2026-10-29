const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("BlockTrace", () => {
  let c, admin, dept, vendor, sub, outsider;
  const purpose = ethers.keccak256(ethers.toUtf8Bytes("road-repair-invoice-42"));

  beforeEach(async () => {
    [admin, dept, vendor, sub, outsider] = await ethers.getSigners();
    const F = await ethers.getContractFactory("BlockTrace");
    c = await F.deploy(admin.address);
  });

  async function allocate(amount = 1000n) {
    const tx = await c.allocate(dept.address, amount, purpose);
    const r = await tx.wait();
    return r.logs.find((l) => l.fragment?.name === "TokenCreated").args.tokenId;
  }

  it("creates a unique token per allocation", async () => {
    const a = await allocate();
    const b = await allocate();
    expect(a).to.not.equal(b);
    expect(await c.totalTokens()).to.equal(2n);
  });

  it("links child tokens to parent and tracks remaining funds", async () => {
    const root = await allocate(1000n);
    const tx = await c.connect(dept).forwardFunds(root, vendor.address, 400n, purpose);
    const r = await tx.wait();
    const child = r.logs.find((l) => l.fragment?.name === "TokenCreated").args.tokenId;
    expect((await c.getToken(root)).remaining).to.equal(600n);
    expect(await c.childrenOf(root)).to.deep.equal([child]);
    const [origin, depth] = await c.originOf(child);
    expect(origin).to.equal(root);
    expect(depth).to.equal(1n);
  });

  it("rejects forwarding more than remains", async () => {
    const root = await allocate(100n);
    await expect(c.connect(dept).forwardFunds(root, vendor.address, 101n, purpose))
      .to.be.revertedWithCustomError(c, "InsufficientRemaining");
  });

  it("rejects forwarding by someone who does not hold the token", async () => {
    const root = await allocate();
    await expect(c.connect(outsider).forwardFunds(root, vendor.address, 1n, purpose))
      .to.be.revertedWithCustomError(c, "NotHolder");
  });

  it("only operators allocate and only auditors change status", async () => {
    await expect(c.connect(outsider).allocate(dept.address, 1n, purpose)).to.be.reverted;
    const root = await allocate();
    await expect(c.connect(outsider).setStatus(root, 1, "x")).to.be.reverted;
    await c.setStatus(root, 1, "suspicious split");
    expect((await c.getToken(root)).status).to.equal(1n);
  });

  it("blocks forwarding of frozen tokens", async () => {
    const root = await allocate();
    await c.setStatus(root, 2, "frozen pending investigation");
    await expect(c.connect(dept).forwardFunds(root, vendor.address, 1n, purpose))
      .to.be.revertedWithCustomError(c, "TokenFrozen");
  });

  it("anchors each merkle root once", async () => {
    const root = ethers.keccak256(ethers.toUtf8Bytes("batch-1"));
    await c.anchorRoot(root, 10);
    expect(await c.anchoredAt(root)).to.be.gt(0n);
    await expect(c.anchorRoot(root, 10)).to.be.revertedWithCustomError(c, "AlreadyAnchored");
  });

  it("can be paused by the admin", async () => {
    await c.pause();
    await expect(c.allocate(dept.address, 1n, purpose)).to.be.reverted;
  });
});
