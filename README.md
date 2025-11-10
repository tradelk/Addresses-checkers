# Wallet Interrupted-Transaction & Sybil Checker

Simple Python app that:
1. Loads a list of wallet addresses from a text file (one address per line).
2. Checks each address for interrupted or failed transactions (using Etherscan API).
3. Detects potential *sybil* addresses (addresses that interact with 2 or more of the input wallets).
4. Presents results in the console and saves a CSV report.

**Notes & limitations**
- By default the app uses the Etherscan API. You must provide an `ETHERSCAN_API_KEY` (environment variable or command-line option).
- "Interrupted transactions" in this simple tool are treated as transactions with an error status (failed) according to Etherscan. Pending transactions require an Ethereum node RPC (web3) and are not fully supported in this minimal implementation.
- This is a starter project — you can extend it to use Alchemy/Infura or to inspect mempool/pending transactions for more complete "interrupted" detection.

## Files
- `main.py` — main application
- `wallets.txt` — example wallets file
- `requirements.txt` — needed Python packages
- `.gitignore` — git ignore
