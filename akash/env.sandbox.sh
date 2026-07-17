# Akash sandbox-2 testnet config. Source this before running provider-services:
#   source akash/env.sandbox.sh
# Endpoints pulled from https://github.com/akash-network/net/blob/main/sandbox-2/meta.json

export AKASH_NET="https://raw.githubusercontent.com/akash-network/net/main/sandbox-2"
export AKASH_CHAIN_ID="sandbox-2"
export AKASH_NODE="https://rpc.sandbox-2.aksh.pw:443"
export AKASH_API_NODE="https://api.sandbox-2.aksh.pw:443"
export AKASH_FAUCET="http://faucet.sandbox-2.aksh.pw/"
export AKASH_EXPLORER="https://explorer.sandbox-2.aksh.pw/akash"

# Wallet / signing. 'test' keyring is file-based (no macOS keychain prompt) —
# fine for a free testnet key that never holds real funds.
export AKASH_KEYRING_BACKEND="test"
export AKASH_KEY_NAME="swarm-sandbox"

# Tx defaults for sandbox-2 (min gas price 0.00025 uakt).
export AKASH_GAS="auto"
export AKASH_GAS_ADJUSTMENT="1.5"
export AKASH_GAS_PRICES="0.025uakt"
export AKASH_SIGN_MODE="amino-json"
export AKASH_YES="true"

echo "Akash env loaded: chain=$AKASH_CHAIN_ID node=$AKASH_NODE key=$AKASH_KEY_NAME"
