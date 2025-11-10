#!/usr/bin/env python3
"""
Simple Wallet Interrupted-Transaction & Sybil Checker

Usage:
    python main.py --wallets wallets.txt --apikey YOUR_ETHERSCAN_API_KEY

Environment:
    You can set ETHERSCAN_API_KEY in environment or pass --apikey.

Notes:
    - The script uses the Etherscan "txlist" endpoint to fetch historical transactions.
    - Interrupted / failed transactions are detected by `isError` or `txreceipt_status` fields.
    - Sybil detection (basic): addresses that interact with >= 2 of the input wallets are marked as potential sybils.
"""
import argparse
import os
import requests
import time
import pandas as pd
from collections import defaultdict, Counter
from tabulate import tabulate
from dotenv import load_dotenv

load_dotenv()

ETHERSCAN_API = "https://api.etherscan.io/api"

def read_wallets(path):
    with open(path, "r") as f:
        addrs = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    # basic normalization
    addrs = [a if a.startswith("0x") else "0x"+a for a in addrs]
    return addrs

def fetch_txs_etherscan(address, api_key, startblock=0, endblock=99999999, page=1, offset=10000, sort="asc"):
    params = {
        "module":"account",
        "action":"txlist",
        "address":address,
        "startblock":startblock,
        "endblock":endblock,
        "page":page,
        "offset":offset,
        "sort":sort,
        "apikey":api_key
    }
    resp = requests.get(ETHERSCAN_API, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "0" and data.get("message","").lower().startswith("no transactions"):
        return []
    if data.get("status") not in ("0","1"):
        raise RuntimeError(f"Etherscan returned unexpected status for {address}: {data}")
    return data.get("result", [])

def analyze_wallets(wallets, api_key, max_txs_per_wallet=10000, delay_between_calls=0.2):
    interrupted = defaultdict(list)  # wallet -> list of interrupted txs
    counterparties = defaultdict(set)  # counterparty -> set of wallets it interacted with
    all_txs = []

    for w in wallets:
        try:
            txs = fetch_txs_etherscan(w, api_key, offset=max_txs_per_wallet)
        except Exception as e:
            print(f"Error fetching txs for {w}: {e}")
            txs = []
        time.sleep(delay_between_calls)
        for tx in txs:
            # tx is a dict from Etherscan
            tx_record = {
                "wallet": w,
                "hash": tx.get("hash"),
                "from": tx.get("from"),
                "to": tx.get("to"),
                "value": int(tx.get("value", "0")) / 10**18,
                "gas": tx.get("gas"),
                "gasPrice": tx.get("gasPrice"),
                "isError": tx.get("isError"),
                "txreceipt_status": tx.get("txreceipt_status"),
                "blockNumber": tx.get("blockNumber"),
                "timeStamp": tx.get("timeStamp")
            }
            all_txs.append(tx_record)

            # interrupted criteria (basic):
            # - isError == "1"  OR txreceipt_status == "0"
            if tx_record["isError"] == "1" or tx_record["txreceipt_status"] == "0":
                interrupted[w].append(tx_record)

            # counterparties: include both from and to (exclude same as wallet)
            for cp in (tx_record["from"], tx_record["to"]):
                if cp and cp.lower() != w.lower():
                    counterparties[cp.lower()].add(w.lower())
    return interrupted, counterparties, pd.DataFrame(all_txs)

def build_sybil_table(counterparties, threshold=2):
    rows = []
    for addr, wallets in counterparties.items():
        if len(wallets) >= threshold:
            rows.append({"address":addr, "wallet_count":len(wallets), "wallets":",".join(sorted(wallets))})
    if rows:
        df = pd.DataFrame(rows).sort_values(by="wallet_count", ascending=False)
    else:
        df = pd.DataFrame(columns=["address","wallet_count","wallets"])
    return df

def save_reports(interrupted, sybil_df, all_txs_df, outdir="output"):
    os.makedirs(outdir, exist_ok=True)
    # interrupted CSV
    rows = []
    for w, txs in interrupted.items():
        for tx in txs:
            rows.append({
                "wallet": w,
                "hash": tx["hash"],
                "from": tx["from"],
                "to": tx["to"],
                "value_eth": tx["value"],
                "isError": tx["isError"],
                "txreceipt_status": tx["txreceipt_status"],
                "blockNumber": tx["blockNumber"],
                "timeStamp": tx["timeStamp"]
            })
    df_int = pd.DataFrame(rows)
    df_int.to_csv(os.path.join(outdir, "interrupted_transactions.csv"), index=False)
    sybil_df.to_csv(os.path.join(outdir, "potential_sybil_addresses.csv"), index=False)
    all_txs_df.to_csv(os.path.join(outdir, "all_txs.csv"), index=False)
    print(f"Saved reports to {outdir}/")

def main():
    p = argparse.ArgumentParser(description="Wallet Interrupted-Transaction & Sybil Checker")
    p.add_argument("--wallets", "-w", default="wallets.txt", help="text file with one wallet address per line")
    p.add_argument("--apikey", "-k", help="Etherscan API key (or set ETHERSCAN_API_KEY env var)")
    p.add_argument("--sybil-threshold", type=int, default=2, help="minimum number of distinct input wallets a counterparty must touch to be considered potential sybil (default:2)")
    args = p.parse_args()

    api_key = args.apikey or os.environ.get("ETHERSCAN_API_KEY")
    if not api_key:
        print("ERROR: Etherscan API key required. Provide with --apikey or set ETHERSCAN_API_KEY.")
        return

    wallets = read_wallets(args.wallets)
    if not wallets:
        print("No wallets found in", args.wallets)
        return

    print(f"Loaded {len(wallets)} wallets. Querying Etherscan...")
    interrupted, counterparties, all_txs_df = analyze_wallets(wallets, api_key)
    # Summarize interrupted
    for w in wallets:
        its = interrupted.get(w, [])
        print(f"\nWallet: {w} -> interrupted/failed txs: {len(its)}")
        if its:
            print(tabulate([ (t['hash'], t['from'], t['to'], t['value'], t['isError'], t['txreceipt_status']) for t in its ],
                           headers=["hash","from","to","value_eth","isError","txreceipt_status"]))

    sybil_df = build_sybil_table(counterparties, threshold=args.sybil_threshold)
    if not sybil_df.empty:
        print("\nPotential sybil addresses (interacted with >= {} input wallets):".format(args.sybil_threshold))
        print(tabulate(sybil_df.values.tolist(), headers=sybil_df.columns))
    else:
        print("\nNo potential sybil addresses found with the given threshold.")

    save_reports(interrupted, sybil_df, all_txs_df)

if __name__ == "__main__":
    main()
