# Setup and Configuration Guide

This guide provides detailed instructions on how to install, configure, and run the CVDTrader bot.

## 1. Prerequisites

- **Python 3.10+**: Ensure you have Python installed. Use `python --version` to check.
- **Node.js 18+**: Required for the frontend dashboard.
- **Hyperliquid Account**: You need a valid wallet address and private key (or API agent key).
- **Git**: Required to clone the repository.

## 2. Clone the Repository

```bash
git clone https://github.com/welloul/CVDTrader.git
cd CVDTrader
```

## 3. Backend Installation

1. **Clone the repository** (if applicable) or navigate to the `backend` folder.
2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## 4. Configuration (`.env`)

Create a `.env` file in the `backend/` directory by copying `.env.example`.

### Essential Variables

- `HYPERLIQUID_WALLET_ADDRESS`: Your public wallet address.
- `HYPERLIQUID_SECRET_KEY`: Your private key or Agent secret key.
- `EXECUTION_MODE`: 
    - `dryrun`: Scans for setups but does not place trades. (Safest for testing)
    - `testnet`: Trades on the Hyperliquid Testnet.
    - `live`: Trades on Hyperliquid Mainnet.
- `TARGET_COINS`: Comma-separated list of assets to trade (e.g., `BTC,ETH,SOL,ZEC,XMR,LTC`).
- `ACTIVE_STRATEGY`: Set to `delta_poc`.

## 5. Running the Application

### Start the Backend
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```
The backend will start syncing state and connecting to the WebSocket feed.

### Start the Frontend
1. Navigate to the `frontend` folder.
2. Install dependencies: `npm install`
3. Start the dev server: `npm run dev`
4. Open your browser to `http://localhost:5173`.

## 6. Security Recommendations

- **Use API Agents**: We highly recommend using Hyperliquid's "API Agent" feature instead of your primary wallet private key. This allows you to restrict permissions and set a specific "expiry" or "gas" limit.
- **Dryrun First**: Always run the bot in `dryrun` mode for at least 24 hours to ensure your environment and indicators are stable before moving to Testnet or Live.
