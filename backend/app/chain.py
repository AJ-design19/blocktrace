"""Optional on-chain anchoring through web3. If no RPC is configured (or web3 isn't
installed) anchoring still works off-chain and chain_tx stays null."""
from __future__ import annotations

import logging

from .config import get_settings

log = logging.getLogger("blocktrace.chain")
ABI = [{"name": "anchorRoot", "type": "function", "stateMutability": "nonpayable",
        "inputs": [{"name": "root", "type": "bytes32"}, {"name": "leafCount", "type": "uint256"}], "outputs": []}]


def anchor(root_hex: str, leaf_count: int) -> str | None:
    s = get_settings()
    if not (s.chain_rpc_url and s.chain_contract_address and s.chain_private_key):
        return None
    try:
        from web3 import Web3  # noqa: WPS433
        w3 = Web3(Web3.HTTPProvider(s.chain_rpc_url))
        acct = w3.eth.account.from_key(s.chain_private_key)
        c = w3.eth.contract(address=Web3.to_checksum_address(s.chain_contract_address), abi=ABI)
        tx = c.functions.anchorRoot(bytes.fromhex(root_hex), leaf_count).build_transaction({
            "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address)})
        signed = acct.sign_transaction(tx)
        return w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    except Exception as exc:  # never let a chain outage block the ledger
        log.error("On-chain anchoring failed: %s", exc)
        return None
