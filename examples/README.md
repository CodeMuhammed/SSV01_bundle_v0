Examples (regtest skeletons)

This folder contains minimal, commented skeletons to demonstrate the flow.

close_repay_demo.sh (skeleton)
- Assumes bitcoind -regtest is running and wallets vault/borrower/provider exist.
- Derives keys, builds tapscript, and crafts a CLOSE PSBT.
- TapRet (lean): use your RGB tool to produce the anchor scriptPubKey (hex) and value; insert it as an output in the CLOSE PSBT, then run `ssv anchor-verify` before finalizing.
- Finalizes the borrower witness using ssv CLI and prints the raw tx for broadcast.

liq_demo.sh (skeleton)
- Demonstrates the CSV liquidation path after the vault UTXO has enough relative confirmations.
- Crafts a LIQUIDATE PSBT with nSequence=csv_blocks and finalizes provider witness.

Notes
- This demo does not perform RGB operations; integrate your RGB library/tooling where indicated.
- Ensure your PSBT has witness_utxo (use walletprocesspsbt in Core if needed).
 - For TapRet anchoring, keep the anchor output (index, spk, value) unchanged across fee bumps.
