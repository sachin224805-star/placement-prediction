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

# Install Python requirements
python3 -m pip install --no-cache-dir flask flask-cors pandas scikit-learn joblib openpyxl gunicorn

echo '=== Python packages installed ==='

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

# Start and enable services
systemctl daemon-reload
systemctl enable placement-app
systemctl start placement-app
systemctl enable nginx
systemctl start nginx

echo '=== Services started ==='
echo '=== Placement App Deployment Complete! ==='
