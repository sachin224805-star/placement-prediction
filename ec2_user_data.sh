#!/bin/bash
set -e
exec > >(tee -a /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo '=== Starting Placement App Deployment ==='

# Setup 2GB Swap
if [ ! -f /swapfile ]; then
    dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile swap swap defaults 0 0' >> /etc/fstab
fi

# Fix curl conflict: Amazon Linux 2023 ships curl-minimal
# Swap it out before installing full curl
dnf update -y
dnf swap -y curl-minimal curl || true
dnf install -y python3 python3-pip nginx tar

echo '=== Packages installed ==='

# Setup application directory
mkdir -p /opt/placement-app
cd /opt/placement-app

# Download app bundle from S3 using AWS CLI (no curl needed)
echo 'Downloading application bundle from S3...'
aws s3 cp s3://placement-app-833116001856/placement_app.tar.gz /opt/placement-app/placement_app.tar.gz
tar -xzf placement_app.tar.gz
echo 'App extracted.'

# Install Python requirements (pymysql talks to the private RDS instance)
python3 -m pip install --no-cache-dir flask flask-cors pymysql cryptography pandas scikit-learn joblib openpyxl gunicorn

echo '=== Python packages installed ==='

# --- RDS connection settings -------------------------------------------------
# Set DB_HOST to the endpoint shown in the RDS console. Do not commit a real
# password here; supply it out of band via /etc/placement-app.env instead.
DB_HOST="${DB_HOST:-}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-admin}"
DB_NAME="${DB_NAME:-studentdb}"
DB_PASSWORD="${DB_PASSWORD:-}"

if [ -z "$DB_PASSWORD" ] && [ -f /etc/placement-app.env ]; then
    # Password supplied separately so it never lands in user data or Git.
    . /etc/placement-app.env
fi

echo "=== RDS target: ${DB_HOST:-not configured} ==="

# Configure Nginx reverse proxy (clean config)
cat > /etc/nginx/conf.d/placement.conf << 'NGINXEOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
NGINXEOF

# Disable the default server block that conflicts on port 80
sed -i 's/listen       80 default_server;/listen       8080 default_server;/g' /etc/nginx/nginx.conf 2>/dev/null || true
sed -i 's/listen       \[::\]:80 default_server;/listen       [::]:8080 default_server;/g' /etc/nginx/nginx.conf 2>/dev/null || true

echo '=== Nginx configured ==='

# Configure systemd service for Gunicorn
cat > /etc/systemd/system/placement-app.service << 'SVCEOF'
[Unit]
Description=Placement & Backlog Prediction Web App
After=network.target

[Service]
User=root
WorkingDirectory=/opt/placement-app
ExecStart=/usr/local/bin/gunicorn --workers 2 --bind 127.0.0.1:5000 --timeout 120 server:app
Restart=always
RestartSec=5
Environment=PORT=5000
Environment=PYTHONUNBUFFERED=1
[Install]
WantedBy=multi-user.target
SVCEOF
# Pass the RDS settings to systemd, and keep the password in a root-only file
# that the EnvironmentFile directive below reads at start time.
if [ -n "$DB_HOST" ]; then
    {
        echo "DB_HOST=$DB_HOST"
        echo "DB_PORT=$DB_PORT"
        echo "DB_USER=$DB_USER"
        echo "DB_NAME=$DB_NAME"
        echo "DB_PASSWORD=$DB_PASSWORD"
    } > /etc/placement-app.env
    chmod 600 /etc/placement-app.env
    sed -i "/^Environment=PYTHONUNBUFFERED/i EnvironmentFile=-/etc/placement-app.env" /etc/systemd/system/placement-app.service
fi

# Start and enable services
systemctl daemon-reload
systemctl enable placement-app
systemctl start placement-app
systemctl enable nginx
systemctl start nginx

# Report whether the app reached RDS, so a failed connection is visible in the boot log.
if [ -n "$DB_HOST" ]; then
    echo "=== Checking RDS connectivity to $DB_HOST:$DB_PORT ==="
    (dnf install -y mariadb105 >/dev/null 2>&1 || true)
    if mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" \
        -e "USE $DB_NAME; SELECT COUNT(*) AS students FROM students;" 2>/dev/null; then
        echo '=== RDS reachable and students table present ==='
    else
        echo '=== RDS NOT reachable; app will use the JSON store ==='
    fi
fi

echo '=== Services started ==='
echo '=== Placement App Deployment Complete! ==='
