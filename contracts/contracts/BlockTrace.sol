// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title BlockTrace
/// @notice Every transaction gets a unique cryptographic token. Funds that move on
///         are linked to their parent token, so the whole money trail can be walked
///         from the original allocation to the final beneficiary.
contract BlockTrace is AccessControl, Pausable, ReentrancyGuard {
    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");
    bytes32 public constant AUDITOR_ROLE = keccak256("AUDITOR_ROLE");

    enum Status { Active, Flagged, Frozen, Cleared }

    struct TokenRecord {
        bytes32 tokenId;
        bytes32 parentId;       // bytes32(0) for an original allocation
        address from;
        address to;
        uint256 amount;
        uint256 remaining;      // amount not yet forwarded to child tokens
        uint64 timestamp;
        bytes32 purposeHash;    // keccak256 of off-chain purpose / invoice reference
        Status status;
    }

    mapping(bytes32 => TokenRecord) private _tokens;
    mapping(bytes32 => bytes32[]) private _children;
    mapping(address => bytes32[]) private _byAccount;
    mapping(bytes32 => uint64) public anchoredAt; // merkle root => timestamp
    uint256 public totalTokens;
    uint256 private _nonce;

    event TokenCreated(bytes32 indexed tokenId, bytes32 indexed parentId, address indexed from, address to, uint256 amount);
    event StatusChanged(bytes32 indexed tokenId, Status previous, Status current, address indexed by, string reason);
    event RootAnchored(bytes32 indexed root, uint256 leafCount, address indexed by);

    error UnknownToken(bytes32 tokenId);
    error InsufficientRemaining(bytes32 tokenId, uint256 remaining, uint256 requested);
    error NotHolder(bytes32 tokenId, address caller);
    error TokenFrozen(bytes32 tokenId);
    error ZeroAmount();
    error ZeroAddress();
    error AlreadyAnchored(bytes32 root);

    constructor(address admin) {
        if (admin == address(0)) revert ZeroAddress();
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(OPERATOR_ROLE, admin);
        _grantRole(AUDITOR_ROLE, admin);
    }

    /// @notice Create an original allocation (e.g. a budget release).
    function allocate(address to, uint256 amount, bytes32 purposeHash)
        external onlyRole(OPERATOR_ROLE) whenNotPaused returns (bytes32 tokenId)
    {
        if (to == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        tokenId = _mint(bytes32(0), msg.sender, to, amount, purposeHash);
    }

    /// @notice The holder of a token forwards part of it. A child token is minted and
    ///         linked to its parent, so the money trail is never broken.
    function forwardFunds(bytes32 parentId, address to, uint256 amount, bytes32 purposeHash)
        external whenNotPaused nonReentrant returns (bytes32 tokenId)
    {
        TokenRecord storage parent = _tokens[parentId];
        if (parent.timestamp == 0) revert UnknownToken(parentId);
        if (parent.to != msg.sender) revert NotHolder(parentId, msg.sender);
        if (parent.status == Status.Frozen) revert TokenFrozen(parentId);
        if (to == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        if (amount > parent.remaining) revert InsufficientRemaining(parentId, parent.remaining, amount);

        parent.remaining -= amount;
        tokenId = _mint(parentId, msg.sender, to, amount, purposeHash);
        _children[parentId].push(tokenId);
    }

    /// @notice Auditors mark a token (and later clear or freeze it) with a reason.
    function setStatus(bytes32 tokenId, Status newStatus, string calldata reason)
        external onlyRole(AUDITOR_ROLE)
    {
        TokenRecord storage t = _tokens[tokenId];
        if (t.timestamp == 0) revert UnknownToken(tokenId);
        Status previous = t.status;
        t.status = newStatus;
        emit StatusChanged(tokenId, previous, newStatus, msg.sender, reason);
    }

    /// @notice Anchor the Merkle root of an off-chain batch so history cannot be rewritten.
    function anchorRoot(bytes32 root, uint256 leafCount) external onlyRole(OPERATOR_ROLE) {
        if (anchoredAt[root] != 0) revert AlreadyAnchored(root);
        anchoredAt[root] = uint64(block.timestamp);
        emit RootAnchored(root, leafCount, msg.sender);
    }

    function getToken(bytes32 tokenId) external view returns (TokenRecord memory) {
        if (_tokens[tokenId].timestamp == 0) revert UnknownToken(tokenId);
        return _tokens[tokenId];
    }

    function childrenOf(bytes32 tokenId) external view returns (bytes32[] memory) {
        return _children[tokenId];
    }

    function tokensOf(address account) external view returns (bytes32[] memory) {
        return _byAccount[account];
    }

    /// @notice Walk up to the original allocation. Bounded to avoid unbounded gas use.
    function originOf(bytes32 tokenId) external view returns (bytes32 origin, uint256 depth) {
        TokenRecord storage t = _tokens[tokenId];
        if (t.timestamp == 0) revert UnknownToken(tokenId);
        origin = tokenId;
        while (t.parentId != bytes32(0) && depth < 64) {
            origin = t.parentId;
            t = _tokens[origin];
            depth++;
        }
    }

    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) { _pause(); }
    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) { _unpause(); }

    function _mint(bytes32 parentId, address from, address to, uint256 amount, bytes32 purposeHash)
        private returns (bytes32 tokenId)
    {
        tokenId = keccak256(abi.encode(parentId, from, to, amount, purposeHash, block.timestamp, ++_nonce));
        _tokens[tokenId] = TokenRecord({
            tokenId: tokenId,
            parentId: parentId,
            from: from,
            to: to,
            amount: amount,
            remaining: amount,
            timestamp: uint64(block.timestamp),
            purposeHash: purposeHash,
            status: Status.Active
        });
        _byAccount[to].push(tokenId);
        totalTokens++;
        emit TokenCreated(tokenId, parentId, from, to, amount);
    }
}
