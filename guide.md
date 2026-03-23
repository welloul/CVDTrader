# CVDTrader Bot Deployment Guide for AWS VPS (Amazon Linux)

This guide provides step-by-step instructions for deploying the CVDTrader bot on an AWS VPS running Amazon Linux. Two deployment options are provided:
1. Backend-only (API service only)
2. Backend + Frontend (full stack with UI)

## Prerequisites

Before beginning, ensure you have:
- An AWS EC2 instance running Amazon Linux 2
- SSH access to the instance
- Basic familiarity with Linux command line
- Hyperliquid API credentials (for live/testnet trading)

## Option 1: Backend-Only Deployment

This option deploys only the backend API service. You can control and monitor the bot entirely from the terminal using curl commands or HTTP requests.

### Step 1: Connect to Your AWS Instance
```bash
ssh -i your-key.pem ec2-user@your-ec2-public-dns
```

### Step 2: Update System Packages
```bash
sudo yum update -y
```

### Step 3: Install Required Dependencies
```bash
# Install Python 3.8+ and pip
sudo yum install -y python3 python3-pip git

# Install Node.js (needed for some build tools, even for backend-only)
curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
sudo yum install -y nodejs

# Verify installations
python3 --version
pip3 --version
node --version
npm --version
```

### Step 4: Clone the Repository
```bash
git clone https://github.com/your-username/CVDTrader.git
cd CVDTrader
```

### Step 5: Set Up Python Virtual Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### Step 6: Install Backend Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### Step 7: Configure Environment Variables
```bash
# Copy example environment file
cp .env.example .env

# Edit the .env file with your configuration
nano .env
```

Configure the following in `.env`:
```
# Execution Mode: live, testnet, dryrun
EXECUTION_MODE=dryrun

# Active Strategy to run (e.g., delta_poc)
ACTIVE_STRATEGY=delta_poc

# Target Coins to trade (comma-separated)
TARGET_COINS=BTC,ETH,SOL

# Risk Parameters
MAX_LATENCY_MS=5000
MAX_DRAWDOWN_PCT=5.0
MAX_POSITION_SIZE_USD=50
MAX_LEVERAGE=5

# Hyperliquid API Keys
# You MUST set these if you want to trade (even on testnet)
# Get testnet keys from testnet.hyperliquid.xyz
HYPERLIQUID_SECRET_KEY=your_secret_key_here
HYPERLIQUID_WALLET_ADDRESS=your_wallet_address_here
HYPERLIQUID_MAIN_WALLET_ADDRESS=your_wallet_address_here  # Optional
```

> **Important**: For live trading, replace the testnet values with your actual Hyperliquid API keys. For testing, use testnet.hyperliquid.xyz to get testnet keys.

### Step 8: Test the Backend Installation
```bash
# Start the backend server
uvicorn main:app --host 0.0.0.0 --port 8000

# In another terminal tab/window, test the API:
curl http://localhost:8000/api/status
```

You should see a JSON response with bot status information.

### Step 9: Set Up as a System Service (Recommended for Production)
Create a systemd service file to manage the backend automatically:

```bash
# Create the service file
sudo nano /etc/systemd/system/cvdtrader-backend.service
```

Add the following content:
```
[Unit]
Description=CVDTrader Trading Bot Backend
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/CVDTrader/backend
EnvironmentFile=/home/ec2-user/CVDTrader/backend/.env
ExecStart=/home/ec2-user/CVDTrader/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start the service:
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable cvdtrader-backend.service

# Start the service
sudo systemctl start cvdtrader-backend.service

# Check status
sudo systemctl status cvdtrader-backend.service

# View logs
sudo journalctl -u cvdtrader-backend.service -f
```

### Step 10: Managing the Bot from Terminal

Once the backend is running, you can control the bot using curl commands:

**Start the bot:**
```bash
curl -X POST http://localhost:8000/api/start
```

**Stop the bot:**
```bash
curl -X POST http://localhost:8000/api/stop
```

**Check bot status:**
```bash
curl http://localhost:8000/api/status
```

**Get detailed information:**
```bash
# Get monitored coins
curl http://localhost:8000/api/coins

# Get trade history
curl http://localhost:8000/api/trades

# Get latency stats
curl http://localhost:8000/api/latency
```

**Update configuration via terminal:**
```bash
curl -X POST http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{"max_leverage": 10, "max_position_size_usd": 100}'
```

### Step 11: Monitoring and Logs

**View application logs:**
```bash
sudo journalctl -u cvdtrader-backend.service -f
```

**Check if service is running:**
```bash
sudo systemctl is-active cvdtrader-backend.service
```

**Restart the service:**
```bash
sudo systemctl restart cvdtrader-backend.service
```

**Stop the service:**
```bash
sudo systemctl stop cvdtrader-backend.service
```

### Step 12: Security Considerations

1. **Firewall Configuration**: Only open necessary ports
   ```bash
   # Allow SSH (22) and HTTP API (8000) if needed externally
   sudo firewall-cmd --permanent --add-port=22/tcp
   sudo firewall-cmd --permanent --add-port=8000/tcp
   sudo firewall-cmd --reload
   ```

2. **Consider using a reverse proxy** (NGINX) for SSL termination if exposing the API externally

3. **Keep your .env file secure** - never commit it to version control

## Option 2: Backend + Frontend Deployment

This option deploys both the backend API and frontend UI, giving you a complete web interface in addition to terminal control.

### Steps 1-7: Follow the same steps as Option 1 (Backend-Only)

### Step 8: Set Up Frontend
```bash
# Go to frontend directory
cd ../frontend

# Install frontend dependencies
npm install

# Build for production (optional, for development you can use dev server)
npm run build
```

### Step 9: Configure Environment Variables for Both
Ensure both backend/.env and frontend/.env (if needed) are configured properly.
The frontend primarily connects to the backend via WebSocket, so make sure the backend is accessible.

### Step 10: Set Up Both Services as Systemd Services

**Backend Service** (same as Option 1, Step 9):
```bash
sudo nano /etc/systemd/system/cvdtrader-backend.service
```
[Same content as Option 1]

**Frontend Service**:
```bash
sudo nano /etc/systemd/system/cvdtrader-frontend.service
```

Add the following content:
```
[Unit]
Description=CVDTrader Trading Bot Frontend
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/CVDTrader/frontend
Environment=NODE_ENV=production
ExecStart=/home/ec2-user/CVDTrader/frontend/node_modules/.bin/vite --host --port 5173
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

> **Note**: For production, you might want to serve the built frontend files with a web server like NGINX instead of running Vite directly.

Enable and start both services:
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable both services
sudo systemctl enable cvdtrader-backend.service
sudo systemctl enable cvdtrader-frontend.service

# Start both services
sudo systemctl start cvdtrader-backend.service
sudo systemctl start cvdtrader-frontend.service

# Check status of both
sudo systemctl status cvdtrader-backend.service
sudo systemctl status cvdtrader-frontend.service
```

### Step 11: Accessing the Application

- **Backend API**: http://your-ec2-public-dns:8000
- **Frontend UI**: http://your-ec2-public-dns:5173
- **API Documentation**: http://your-ec2-public-dns:8000/docs (FastAPI auto-generated docs)

### Step 12: Managing the Bot

You can still control the bot from terminal using the same curl commands as in Option 1:
```bash
# Start bot
curl -X POST http://localhost:8000/api/start

# Stop bot
curl -X POST http://localhost:8000/api/stop

# Check status
curl http://localhost:8000/api/status
```

Additionally, you can use the web interface at http://your-ec2-public-dns:5173 to start/stop the bot and monitor its performance.

### Step 13: Monitoring Both Services

**Backend logs:**
```bash
sudo journalctl -u cvdtrader-backend.service -f
```

**Frontend logs:**
```bash
sudo journalctl -u cvdtrader-frontend.service -f
```

**Check both services:**
```bash
sudo systemctl status cvdtrader-backend.service cvdtrader-frontend.service
```

## Option 2 Alternative: Using NGINX for Frontend (Recommended for Production)

For better performance and security in production, consider serving the frontend with NGINX:

### Install NGINX
```bash
sudo yum install -y nginx
```

### Build Frontend for Production
```bash
cd frontend
npm run build
# This creates a 'dist' directory with production-ready files
```

### Configure NGINX
```bash
sudo nano /etc/nginx/conf.d/cvdtrader.conf
```

Add:
```
server {
    listen 80;
    server_name your-domain-or-ip;

    location / {
        root /home/ec2-user/CVDTrader/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

Then:
```bash
# Test NGINX configuration
sudo nginx -t

# Start and enable NGINX
sudo systemctl start nginx
sudo systemctl enable nginx
```

Now you can access the frontend on port 80 (standard HTTP) and NGINX will proxy API/WebSocket requests to the backend.

## Troubleshooting

### Common Issues:

1. **Port already in use**:
   ```bash
   # Find what's using the port
   sudo lsof -i :8000
   # Kill the process
   sudo kill -9 PID_NUMBER
   ```

2. **Permission denied errors**:
   ```bash
   # Ensure you own the files
   sudo chown -R ec2-user:ec2-user /home/ec2-user/CVDTrader
   ```

3. **Module not found errors**:
   ```bash
   # Reactivate virtual environment and reinstall
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Service fails to start**:
   ```bash
   # Check service logs
   sudo journalctl -u cvdtrader-backend.service -e
   ```

5. **Connection refused**:
   ```bash
   # Check if backend is running
   sudo systemctl status cvdtrader-backend.service
   # Check if port is listening
   sudo netstat -tlnp | grep :8000
   ```

## AWS-Specific Recommendations

1. **Instance Type**: For light to moderate trading, t3.medium or t3.large is sufficient
2. **Storage**: 20-30 GB SSD is usually adequate
3. **Security Groups**: 
   - Allow SSH (22) from your IP only
   - Allow HTTP (80) and/or HTTPS (443) if exposing frontend
   - Allow custom port (8000) only if needed for direct API access
4. **Elastic IP**: Consider assigning an Elastic IP to avoid IP changes after reboot
5. **Monitoring**: Set up CloudWatch alarms for CPU utilization and status checks
6. **Backups**: Regularly snapshot your EBS volume or backup your configuration files

## Maintenance

1. **Regular Updates**:
   ```bash
   # Pull latest code
   git pull origin main
   
   # Update Python dependencies
   pip install -r requirements.txt
   
   # Update Node.js dependencies (frontend)
   cd ../frontend
   npm install
   ```

2. **Log Rotation**: The journalctl service handles this automatically, but you can configure additional rotation if needed

3. **Periodic Restarts**: Consider scheduling weekly restarts during low-activity periods to clear memory

## Conclusion

You now have the CVDTrader bot deployed on your AWS VPS! 

- **Option 1 (Backend-only)**: Ideal for users who prefer terminal control or want to integrate with other systems via API
- **Option 2 (Backend+Frontend)**: Provides a complete solution with web UI for monitoring and control

Both options allow you to start, stop, and monitor the bot from the terminal using curl commands to the API endpoints, fulfilling your requirement for terminal-based control.

Remember to always test with `EXECUTION_MODE=dryrun` first before switching to live trading!