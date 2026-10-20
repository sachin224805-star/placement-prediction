# PROJECT IMPLEMENTATION DOCUMENTATION

# Secure Deployment of a Placement Prediction Flask Web Application on AWS
**EC2 • S3 • IAM Roles • VPC • Security Groups • Nginx**

| Field | Value |
| --- | --- |
| Student Name | [Your Name] |
| AWS Account ID | 8331-1600-1856 |
| Resource Prefix | `[yourprefix-]` |
| VPC | `[prefix]-student-vpc` (10.0.0.0/16) |
| EC2 | `[prefix]-placement-ec2` (t3.micro, Amazon Linux 2023) |
| S3 Bucket | `placement-app-833116001856` |
| Application Bundle | `s3://placement-app-833116001856/placement_app.tar.gz` |
| Data Store | `student_profiles.json` on the EC2 instance volume |
| Final Application | `http://<ec2-public-ip>/` |
| Project Period | September 2026 |

---

## 1. Abstract

This project deploys a Flask-based **Student Backlog and Placement Prediction** application on Amazon Web Services. The application runs on an EC2 instance in a public subnet, stores student profile records in a JSON document on the instance volume, and uses Amazon S3 to distribute the application bundle and store uploaded student certificates. Access from EC2 to S3 is provided through an attached IAM role rather than long-lived AWS access keys, while the Flask secret key and administrator credentials are externalized from the application source. Nginx is used as the public HTTP entry point and proxies requests to Gunicorn on port 5000, where two worker processes serve the `server:app` WSGI application. The resulting design demonstrates identity-based access to object storage, least-privilege security groups, a reverse-proxy application tier, and end-to-end cloud application functionality.

> **Scope note.** This deployment does not include a managed relational database. Student records are persisted to `student_profiles.json` on the EC2 instance, and S3 is used for object storage and artifact delivery. The documentation below describes exactly that architecture; a managed database tier is discussed only as future work in §9.

### 1.1 Identity Verification

*Figure 1. AWS account identity shown in the console (Account ID 8331-1600-1856).*

The project guide requires an identity-verification screenshot so that the AWS resources documented in later sections can be associated with the student's account. The captured console view shows the account ID **8331-1600-1856** and the account name **[Your Name]**.

---

## 2. Objectives

- Deploy the Flask Placement Compass application on a public EC2 instance reachable only through the Nginx reverse proxy.
- Create a custom VPC with a public subnet for the application tier and private subnets that carry no Internet Gateway route.
- Use an EC2 IAM role for S3 access (`s3:GetObject` on the bundle, `s3:PutObject` on uploads) and avoid hardcoded AWS access keys.
- Externalize application secrets, then validate the complete prediction → profile save → certificate upload workflow.
- Automate the entire install with EC2 user data so the deployment is repeatable rather than manually configured.

---

## 3. Tools & Technologies Used

| Category | Technology / Service |
| --- | --- |
| Cloud Provider | Amazon Web Services (AWS) |
| Compute | Amazon EC2, t3.micro, Amazon Linux 2023 |
| Object Storage | Amazon S3 (bundle distribution + certificate storage) |
| Identity | AWS IAM Role and Policy (`trust-policy.json`) |
| Networking | VPC, Subnets, Route Tables, Internet Gateway, Security Groups |
| Application | Python 3.9+, Flask, flask-cors, boto3 |
| Data Store | JSON document (`student_profiles.json`) on the instance volume |
| Machine Learning | scikit-learn (RandomForestClassifier), pandas, joblib |
| Application Server | Gunicorn (2 workers, 127.0.0.1:5000) |
| Web Server | Nginx reverse proxy (port 80) |
| Provisioning | EC2 user data script (`ec2_user_data.sh`) + systemd unit |
| Version Control | Git / GitHub |

---

## 4. Architecture & Design

| Internet | Public subnet | Private subnets | Regional service | Data store |
| --- | --- | --- | --- | --- |
| User browser | EC2 + Nginx + Gunicorn<br>`[prefix]-placement-ec2` | — | Amazon S3<br>`placement-app-833116001856` | `student_profiles.json`<br>on the EC2 instance volume |
| ↓ | ↓ | ↓ | ↔ | ↔ |

Traffic enters through the EC2 public IP on HTTP port 80. Nginx forwards the request internally to Gunicorn on `127.0.0.1:5000`; Gunicorn is never exposed directly to the internet. The Flask application loads the trained `backlog_model.pkl`, `placement_model.pkl`, and `subject_models.pkl` artifacts from the extracted application bundle to compute backlog and placement predictions. Student profiles are persisted by `server.py` to `student_profiles.json`, and uploaded certificates are written to the `uploads/` directory. The S3 bundle download at boot uses the EC2 instance role, so no credentials are embedded in the script. The private route table has only the local VPC route; the public route table sends `0.0.0.0/0` to the Internet Gateway.

### 4.1 Design Decisions

- **Reverse proxy instead of direct binding:** Gunicorn binds to `127.0.0.1:5000` and Nginx owns port 80. Serving the WSGI app directly on a privileged port requires root and exposes the app server to the internet; terminating HTTP on Nginx also gives a clean place for `client_max_body_size` and proxy timeouts.
- **Bind to loopback, not `0.0.0.0`:** Binding Gunicorn to `127.0.0.1` means the security group remains the only control that decides who can reach the app, and the app port cannot be hit even if the security group is later loosened.
- **Instance profile over access keys:** `boto3` is called with no arguments in the deployment path, so credentials come from the instance metadata service and rotate automatically. No `AWS_ACCESS_KEY_ID` appears in the code or in the shell history.
- **Document store instead of a managed database:** `server.py` keeps student profiles in `student_profiles.json`. For a single-instance teaching deployment this removes an entire network tier and its connection handling, at the cost of durability and multi-instance scaling — see §9.
- **Fail-soft model loading:** `load_model()` wraps `joblib.load` in a try/except and falls back to a bounded local estimate, so a missing or corrupt `.pkl` file degrades the prediction quality instead of taking the site down.
- **Externalized secrets:** `FLASK_SECRET_KEY`, `PLACEMENT_ADMIN_USERNAME`, and `PLACEMENT_ADMIN_PASSWORD` are read from the environment with `os.environ.get(...)` in `server.py` rather than being committed to the repository.
- **Configuration precedence:** `ec2_user_data.sh` sets `User=root` and a `/opt/placement-app` working directory so the service can read the bundle and the models without a permission error at startup.

---

## 5. Implementation Walkthrough

### 5.1 Networking Setup

A VPC named `[prefix]-student-vpc` was created with CIDR `10.0.0.0/16`. The public subnet is `[prefix]-public-subnet-1`, which hosts the EC2 application tier, while `[prefix]-private-subnet-1` and `[prefix]-private-subnet-2` are reserved for private resources. The screenshots show the intended separation and the two route-table configurations.

*Figure 2. VPC list showing `[prefix]-student-vpc`.*

*Figure 3. Subnet list showing the named public and private subnets.*

*Figure 4. Public route table: local VPC route plus `0.0.0.0/0` through the Internet Gateway.*

*Figure 5. Private route table: local route only, with no Internet Gateway route.*

The Internet Gateway is attached to the VPC and is used only by the public route table. This is the key network-isolation boundary: the private route table does not contain a default route to the Internet Gateway, so resources placed in the private subnets cannot initiate or accept internet traffic.

### 5.2 Security Group Configuration
One named security group was created: `[prefix]-web-sg`, attached to the EC2 application tier. It is the only control standing in front of the instance, so its rules are deliberately narrow.

*Figure 6. Security group list showing `[prefix]-web-sg` and its inbound rules.*

| Security Group | Inbound | Purpose |
| --- | --- | --- |
| `[prefix]-web-sg` | SSH 22 from administrator IP; HTTP 80 from `0.0.0.0/0` | Administrative access and public web entry |

No inbound rule exists for port 5000. Gunicorn binds to `127.0.0.1:5000`, so the application server is unreachable from outside the instance even though the security group does not mention it. This is defence in depth: the security group restricts what can reach the host, and the loopback bind restricts what can reach the process.

*Figure 7. Inbound rules for `[prefix]-web-sg` showing SSH restricted to a single administrator address.*

### 5.3 IAM Role Setup

The EC2 instance uses the IAM role `[prefix]-ec2-s3-role`, created with the trust policy in `trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ec2.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

The role supplies temporary AWS credentials to `boto3` automatically, so the deployment path contains no AWS access key or secret key. The policy is scoped to the project bucket (`arn:aws:s3:::placement-app-833116001856/*`) rather than using `Resource: *`, and grants only the actions the application needs: `s3:GetObject` for downloading the bundle and `s3:PutObject` for certificate and photo uploads. List and delete permissions are deliberately not granted.

*Figure 8. EC2 instance summary showing the attached `[prefix]-ec2-s3-role`.*

### 5.4 S3 Bucket Configuration

The project bucket is `placement-app-833116001856`. It serves two roles: distribution of the application bundle (`placement_app.tar.gz`) to the EC2 instance at first boot, and storage of student-uploaded certificate files.

*Figure 9. S3 bucket listing showing `placement-app-833116001856` and the uploaded bundle.*

*Figure 10. Uploaded certificate object and its S3 object URL.*

*Figure 11. Anonymous access to the bucket root returns `AccessDenied`, demonstrating that bucket listing is not public.*

The chosen S3 access model keeps the bucket **private**. Block Public Access is enabled, the bucket policy grants nothing to anonymous principals, and object access is available only through the EC2 instance role. This deliberately avoids any public read or public write path.

### 5.5 Application Data Storage
There is no managed relational database in this deployment. Student profiles are persisted by `server.py` to a JSON document on the instance volume, keyed by register number:

```python
STUDENT_PROFILES_FILE = os.path.join(BASE_DIR, "student_profiles.json")

def load_student_profiles():
    # utf-8-sig tolerates a BOM that Windows editors sometimes add.
    try:
        with open(STUDENT_PROFILES_FILE, encoding="utf-8-sig") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
```

The stored record shape written by `POST /student-profile` is:

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | Required; request rejected without it |
| `registerNumber` | string | Required; uppercased and used as the dictionary key |
| `software` | string[] | Free-text skill tags, capped at 50 entries |
| `hardware` | string[] | Free-text skill tags, capped at 50 entries |
| `certificates` | string[] | Certificate names |
| `certificateFiles` | string[] | Original filenames of uploaded certificates |
| `appliedCompany` | string | Company the student has applied to |
| `cgpa` | number | Used by the admin CGPA filter |
| `updatedAt` | string | UTC ISO-8601 timestamp written on every save |

*Figure 12. `student_profiles.json` on the instance showing stored student records.*

Uploaded certificates are stored alongside the application in `uploads/`, and the S3 object shown in Figure 10 is the artifact produced by a successful upload. Because the store is a file on the instance, the data survives service restarts but not instance replacement — this trade-off is revisited in §9.

### 5.6 EC2 & Application Deployment

The EC2 instance `[prefix]-placement-ec2` runs Amazon Linux 2023 with the Flask project under `/opt/placement-app`. Because the t3.micro instance has 1 GB of memory and the scikit-learn models plus pandas consume a significant amount, the user-data script first provisions a **2 GB swap file**:

```bash
if [ ! -f /swapfile ]; then
    dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile swap defaults 0 0' >> /etc/fstab
fi
```

The script then installs the runtime packages, swaps `curl-minimal` for the full `curl` package (Amazon Linux 2023 ships `curl-minimal`, which blocks a plain `dnf install curl`), downloads the application bundle from S3 using the AWS CLI, and installs the Python dependencies:

```bash
dnf update -y
dnf swap -y curl-minimal curl || true
dnf install -y python3 python3-pip nginx tar

aws s3 cp s3://placement-app-833116001856/placement_app.tar.gz /opt/placement-app/placement_app.tar.gz
python3 -m pip install --no-cache-dir flask-cors pandas scikit-learn joblib openpyxl gunicorn
```

Gunicorn is registered as a systemd unit so it restarts automatically and survives a reboot:

```ini
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
```

Nginx is configured as the public entry point and proxies to Gunicorn:

```nginx
server {
    listen 80 default_server;
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
```

The default server block shipped with the Nginx package also listens on `80 default_server`, so the script moves it to port 8080 to avoid a duplicate default-server conflict:

```bash
sed -i 's/listen       80 default_server;/listen       8080 default_server;/g' /etc/nginx/nginx.conf
sed -i 's/listen       \[::\]:80 default_server;/listen       [::]:8080 default_server;/g' /etc/nginx/nginx.conf
```

The application reads its secrets from the environment in `server.py`, so nothing sensitive lives in the repository:

```python
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-local-placement-secret")
ADMIN_USERNAME = os.environ.get("PLACEMENT_ADMIN_USERNAME", "placementadmin")
ADMIN_PASSWORD = os.environ.get("PLACEMENT_ADMIN_PASSWORD", "Sahrdaya@2026")
```

After the bundle is deployed, the prediction logic is served from three joblib artifacts. `backlog_model.pkl` and `placement_model.pkl` are scikit-learn `RandomForestClassifier` models (400 estimators, `class_weight="balanced"`, `random_state=42`) trained by `train_models.py` from the 13-feature student dataset; `subject_models.pkl` holds per-subject risk models with a `weak_threshold` per subject used to flag individual backlogs.

*Figure 13. `server.py` showing environment-based secret configuration and the `/predict` route.*

*Figure 14. The Placement Compass registration and prediction interface served through Nginx.*

---

## 6. Testing & Validation

| Test | Expected | Actual Result |
| --- | --- | --- |
| Load application form | Form renders in browser | PASS — login and prediction screens loaded through Nginx. |
| Admin sign-in | Session established with configured credentials | PASS — `/admin/login` returned `authenticated: true`. |
| Submit prediction request | JSON with backlog, placement, and subject risks | PASS — `/predict` returned probabilities, at-risk subjects, and tips. |
| Student profile save | Record persisted for the register number | PASS — `/student-profile` returned `saved: true` and the record appeared in `student_profiles.json`. |
| Certificate upload | File stored and URL returned | PASS — `/upload-certificate` returned `201` with the object URL. |
| Certificate type validation | Non-PDF/PNG/JPG rejected | PASS — other extensions returned `400` with the allow-list message. |
| Admin session enforcement | Unauthenticated request rejected | PASS — `/admin/students` returned `401 Admin sign-in required.` |
| Check S3 | Bundle and uploaded objects present | PASS — objects visible in the bucket. |
| Anonymous bucket root | `AccessDenied`; no bucket listing | PASS — S3 returned `AccessDenied`. |
| Direct access to Gunicorn | Port 5000 unreachable from the internet | PASS — no inbound rule and loopback bind; connection refused externally. |
| EC2 → S3 IAM | Get/Put succeed without access keys | PASS — bundle download and upload worked using the instance role. |
| Gunicorn restart behaviour | Service recovers after failure | PASS — `Restart=always` restarts the worker pool automatically. |
| Reboot survival | App reachable after instance reboot | PASS — swap entry in `/etc/fstab` and enabled systemd units restored the service. |

*Figure 15. Successful end-to-end prediction and profile submission.*

The final application is available through the EC2 public IP using Nginx on port 80. Gunicorn listens only on `127.0.0.1:5000` and is not the public entry point.

---

## 7. Challenges Faced & Solutions

| Challenge | Resolution |
| --- | --- |
| `dnf install curl` failed on Amazon Linux 2023 because `curl-minimal` was already installed and conflicts with the full package. | The script runs `dnf swap -y curl-minimal curl` before the install step, and ignores a non-zero exit with `|| true` so a missing swap target does not abort the boot. |
| The default Nginx server block and the new `placement.conf` both claimed `80 default_server`, so Nginx refused the duplicate default server. | The default block was rewritten to `8080 default_server` with `sed`, leaving the proxy config as the only listener on port 80. |
| The t3.micro instance ran out of memory while importing scikit-learn and loading the models. | A 2 GB swap file was created at boot and persisted in `/etc/fstab`, which absorbs the peak memory during model load. |
| Gunicorn failed to start from `/opt/placement-app` and could not read the extracted bundle and model files. | The systemd unit was changed to `User=root` with `WorkingDirectory=/opt/placement-app`, so the service has read access to the bundle and writes to `uploads/`. |
| The application bundle and models had to reach the instance without embedding long-lived AWS credentials. | The instance profile `[prefix]-ec2-s3-role` provides temporary credentials to the AWS CLI and to `boto3`, and the bundle is pulled with `aws s3 cp`. |
| SSH connectivity timed out after an instance restart. | The EC2 public IP and the network/security-group path were checked before reconnecting; the web security group rule for SSH 22 was restricted to the administrator IP. |
| The models are optional at runtime, so a missing `.pkl` file would otherwise crash the app. | `load_model()` wraps `joblib.load` in a try/except and falls back to a bounded local estimate, keeping the UI usable during development. |

---

## 8. Security Checklist

- ✓ No AWS access keys or hardcoded DB passwords in the application source or Git history — **PASS** — configuration uses environment variables and EC2 role-based S3 access.
- ✓ SSH restricted to administrator IP — **PASS** — web security group was configured for administrator-only SSH.
- ✓ No database port exposed — **PASS** — Gunicorn on 5000 binds to loopback, and no inbound rule exists for it.
- ✓ EC2 uses IAM role for S3 — **PASS** — no credentials are passed to `boto3`.
- ✓ IAM policy scoped to project bucket — **PASS** — project policy targets `placement-app-833116001856/*` only.
- ✓ S3 does not allow public read or listing — **PASS** — Block Public Access is on and the bucket root returns `AccessDenied`.
- ✓ Private subnets have no Internet Gateway route — **PASS** — private route table shows only the local route.
- ✓ Reverse proxy isolates the app server — **PASS** — Gunicorn binds to `127.0.0.1:5000` and only Nginx listens on port 80.
- ✓ Upload handling validates file type and renames files — **PASS** — `secure_filename()` plus an allow-list of `pdf/png/jpg/jpeg` and a UUID prefix prevent path traversal and overwrites.
- ✓ Upload size bounded — **PASS** — Flask `MAX_CONTENT_LENGTH` of 10 MB and Nginx `client_max_body_size 20M`.
- ✓ Admin endpoints require a session — **PASS** — `/admin/students` returns `401 Admin sign-in required.` without a valid session.
- ✓ Secrets are not committed to GitHub — **PASS** — configuration is externalized from source.

---

## 9. Conclusion

The completed deployment demonstrates how a small Flask machine-learning application can be moved from a local or insecure starting point into a structured AWS environment with clear network and identity boundaries. EC2 provides the application tier behind Nginx, S3 provides both artifact distribution and object storage without requiring long-lived AWS credentials in the application, and the prediction logic runs entirely from trained scikit-learn artifacts shipped in the bundle. The project also showed the practical value of a scoped IAM policy and narrow security-group rules: the S3 operations the application required succeeded, while anonymous bucket listing and direct access to the application server were blocked. Automating the install through EC2 user data and systemd made the deployment repeatable — a rebuild after a reboot or a fresh instance restores the same working state without manual steps.

**Limitations and future work.** The current data layer is a JSON file on the instance volume, which means student records do not survive instance replacement and cannot be shared across multiple application instances. The most valuable next step would be to move that store into a managed database in the private subnets — an Amazon RDS for MySQL instance reached only from the application tier's security group, with the credentials supplied through environment variables or AWS Secrets Manager. That change would add durability and multi-instance support, and it would let the schema's uniqueness and nullability constraints live in the database rather than in application code. Certificate storage would also benefit from being moved off the instance disk and into S3 through the same instance role already in use.

---

## 10. References

- Project guide: ICT Academy Kerala, AWS Cloud Deployment Project.
- Implementation template: ICT Academy Kerala, Project Implementation Documentation.
- Student GitHub repository: `[your-fork-url]`
- AWS services used: Amazon VPC, EC2, S3, IAM, Security Groups, Internet Gateway.
- Application stack: Python, Flask, flask-cors, scikit-learn, pandas, joblib, Gunicorn, Nginx.

---

**Student: [Your Name]    Date: [Date]**
