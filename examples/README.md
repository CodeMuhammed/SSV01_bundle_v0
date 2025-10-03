Examples (regtest skeletons)

This folder contains minimal, commented skeletons to demonstrate the flow. The docker image provides the rgb CLI pinned to v0.12.

close_repay_demo.sh (skeleton)
- Assumes bitcoind -regtest is running and wallets vault/borrower/provider exist.
- Derives keys, builds tapscript, and crafts a CLOSE PSBT.
- TapRet (RGB v0.12): prompts you for an RGB invoice and runs `rgb transfer --method tapret` inside the ssv container to update close.psbt. It then auto-detects the new anchor output, runs `ssv anchor-verify`, and proceeds to finalize.
- Finalizes the borrower witness using ssv CLI and prints the raw tx for broadcast.

liq_demo.sh (skeleton)
- Demonstrates the CSV liquidation path after the vault UTXO has enough relative confirmations.
- Crafts a LIQUIDATE PSBT with nSequence=csv_blocks and finalizes provider witness.

Notes
- This demo does not perform RGB operations; integrate your RGB library/tooling where indicated.
- Ensure your PSBT has witness_utxo (use walletprocesspsbt in Core if needed).
 - For TapRet anchoring, keep the anchor output (index, spk, value) unchanged across fee bumps.
