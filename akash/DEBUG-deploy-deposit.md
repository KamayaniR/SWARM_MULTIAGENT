# Akash sandbox-2 — `deployment create` rejected: "Deposit invalid"

## Summary
On the **sandbox-2** testnet, `provider-services tx deployment create` fails at
on-chain message execution with **`Deposit invalid`**, even though the deposit
(`uakt`, ≥ the chain's advertised minimum) matches the `min_deposits` param.
Wallet is funded and the client certificate published successfully, so signing,
gas, node connectivity, and the account itself are all fine. The failure is
specific to `MsgCreateDeployment` deposit validation.

## Environment
| | |
|---|---|
| Client | `provider-services v0.11.1` (Homebrew `akash-network/tap`, darwin/arm64) |
| Chain | `sandbox-2` |
| Node | `https://rpc.sandbox-2.aksh.pw:443` |
| Node app version | Tendermint `2.1.0`, `app_version: 5`, cosmos-sdk `v0.53.6` |
| Account | `akash1at5se6mmlnfp7y4444kmv309zkys5lau9vds5w` |
| Balance | `24996881 uakt` (funded via faucet.sandbox-2.aksh.pw) |

## What works
- `keys add`, faucet funding → balance confirmed on chain.
- `tx cert generate client` + `tx cert publish client` → **success, `code: 0`**
  (tx `414D75D757A2282B7797541FDB76B946E913109991197616AE154B9EF5548C77`).
  (Note: had to raise `--gas-prices` to `0.025uakt`; the documented min
  `0.00025uakt` was rejected as `insufficient fee: got 32uakt required 312uakt`.)

## The failing command
```bash
provider-services tx deployment create deploy.yaml \
  --from swarm-sandbox \
  --deposit 500000uakt \
  --chain-id sandbox-2 \
  --node https://rpc.sandbox-2.aksh.pw:443 \
  --keyring-backend test \
  --gas auto --gas-adjustment 1.5 --gas-prices 0.025uakt -y
```

## Errors observed (in order of what we tried)
1. **No `--deposit` (CLI default):** client-side rejection
   ```
   Error: Mismatched denominations (uact != uakt): Deposit invalid
   ```
   → The CLI's default deposit denom appears to be `uact`, mismatching `uakt`.
2. **`--deposit 5000000uakt`:** chain-side rejection
   ```
   Error: rpc error: code = Unknown desc = ... failed to execute message;
   message index: 0: Deposit invalid
   [cosmos/cosmos-sdk@v0.53.6/baseapp/baseapp.go:1052] with gas used: '34744':
   unknown request
   ```
3. **`--deposit 500000uakt` (exact advertised minimum):** same chain-side
   `Deposit invalid`.

## Chain params say this deposit should be valid
```bash
$ provider-services query deployment params --node https://rpc.sandbox-2.aksh.pw:443 -o json
{"params":{"min_deposits":[
  {"denom":"uact","amount":"500000"},
  {"denom":"uakt","amount":"500000"}
]}}
```
`500000uakt` (and `5000000uakt`) satisfies the `uakt` minimum, yet execution
still returns `Deposit invalid`.

## Our hypothesis / questions for the Akash team
- Looks like a **client/chain version mismatch**: `provider-services v0.11.1`
  vs sandbox-2 running node `v2.1.0` / `app_version 5` / cosmos-sdk `v0.53.6`.
  Did the deployment module's deposit handling change (new proto version, e.g.
  `v1beta4`, or authz/escrow denom rules) in a way v0.11.1 doesn't emit correctly?
- The `uact` vs `uakt` default-denom mismatch suggests the CLI and chain
  disagree on the authorized deposit denom. **What denom + amount + client
  version does sandbox-2 currently expect for `MsgCreateDeployment`?**
- Is there a `provider-services` build matched to the sandbox-2 upgrade we
  should be using instead of the Homebrew `v0.11.1`?

## What we're deploying (SDL) — a stock nginx, just proving the path
`version: "2.0"`, one `web` service `nginx:1.27`, `0.25` cpu / `256Mi` mem /
`256Mi` storage, `global: true` on port 80, pricing `10000 uakt`.
