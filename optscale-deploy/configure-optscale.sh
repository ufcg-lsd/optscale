#!/bin/bash
set -eo pipefail # Exit on error

#================================================================================
# Configuration
# - Please update these variables to match your EKS environment.
#================================================================================
EKS_CLUSTER_NAME="geralados-cluster-1"
AWS_REGION="us-east-1"
CONFIGURE_DTS_DOMAIN=true
DTS_DOMAIN="dts.loc"
DTS_FORWARD_IP="172.22.1.2"


#================================================================================
# Script
#================================================================================

# --- Helper function to check for required commands ---
check_command() {
  if ! command -v "$1" &> /dev/null; then
    echo "🚨 Error: command '$1' not found. Please install it and ensure it's in your PATH."
    exit 1
  fi
}

# --- Main script functions ---

configure_kubeconfig() {
  echo "✅ 1. Configuring kubeconfig for EKS cluster '$EKS_CLUSTER_NAME'..."
  aws eks update-kubeconfig --name "$EKS_CLUSTER_NAME" --region "$AWS_REGION"
  echo "Kubeconfig updated successfully."
}

setup_kubectl_autocomplete() {
  echo "✅ 2. Setting up kubectl bash autocompletion..."
  local BASHRC_PATH="$HOME/.bashrc"
  local AUTOCOMPLETE_LINE='source <(kubectl completion bash)'

  if ! grep -Fxq "$AUTOCOMPLETE_LINE" "$BASHRC_PATH"; then
    echo "$AUTOCOMPLETE_LINE" >> "$BASHRC_PATH"
    echo "Autocompletion added to $BASHRC_PATH. Please run 'source ~/.bashrc' or restart your shell."
  else
    echo "Autocompletion is already configured in $BASHRC_PATH."
  fi
}

install_dashboard() {
  echo "✅ 3. Installing Kubernetes Dashboard..."
  # NOTE: Using a recent, stable version of the dashboard manifest.
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml
  echo "Kubernetes Dashboard deployment initiated."
  echo "ℹ️ Note: To access the dashboard on EKS, you'll need to create an admin user and token, or use an Ingress."
}

install_nginx_and_ssl() {
  echo "✅ 4. Generating SSL certificate for localhost and installing NGINX Ingress..."

  # --- Step 1: Create OpenSSL Configuration ---
  echo "-> Creating OpenSSL configuration file for localhost..."
  cat <<EOF > /tmp/openssl.cfg
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no
[req_distinguished_name]
C = US
ST = California
L = San Francisco
O = MyCompany
OU = IT
CN = localhost
[v3_req]
subjectAltName = @alt_names
[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
EOF

  # --- Step 2: Generate Certificate and Key ---
  echo "-> Generating self-signed SSL certificate and private key..."
  openssl req -x509 -sha256 -nodes -newkey rsa:4096 \
    -keyout /tmp/key.pem \
    -out /tmp/cert.pem \
    -extensions v3_req \
    -days 9001 \
    -config /tmp/openssl.cfg

  # --- Step 3: Create Secret in Kubernetes ---
  echo "-> Creating the 'defaultcert' TLS secret in Kubernetes..."
  kubectl delete secret tls defaultcert --ignore-not-found=true
  kubectl create secret tls defaultcert --key /tmp/key.pem --cert /tmp/cert.pem

  # --- Step 4: Add Bitnami Helm Repo ---
  echo "-> Adding and updating the Bitnami Helm repository..."
  if ! helm repo list | grep -q "bitnami"; then
      helm repo add bitnami https://charts.bitnami.com/bitnami
  fi
  helm repo update

  # --- Step 5: Install NGINX Ingress Controller ---
  echo "-> Installing NGINX Ingress Controller via Helm..."
  # Using the specific version and settings you provided.
  helm upgrade --install ngingress bitnami/nginx-ingress-controller \
    --version "11.3.17" \
    --set hostNetwork=true \
    --set extraArgs.default-ssl-certificate=default/defaultcert \
    --set kind=DaemonSet \
    --set daemonset.useHostPort=true \
    --set containerPorts.http=80 \
    --set containerPorts.https=443 \
    --set resources.limits.memory=896Mi \
    --set resources.requests.memory=384Mi

  # --- Step 6: Clean Up Temporary Files ---
  echo "-> Cleaning up temporary files..."
  rm /tmp/openssl.cfg /tmp/key.pem /tmp/cert.pem

  echo "NGINX Ingress and localhost SSL certificate setup complete."
  echo "ℹ️ Note: The generated SSL certificate is for 'localhost' and is not suitable for production use."
}

configure_coredns() {
  if [[ "$CONFIGURE_DTS_DOMAIN" != "true" ]]; then
    echo "☑️ 5. Skipping CoreDNS configuration."
    return
  fi

  echo "✅ 5. Configuring CoreDNS to forward '$DTS_DOMAIN'..."

  # Check if the domain is already in the CoreDNS config
  if kubectl get configmap coredns -n kube-system -o jsonpath='{.data.Corefile}' | grep -q "$DTS_DOMAIN"; then
    echo "CoreDNS is already configured for $DTS_DOMAIN. Skipping."
    return
  fi

  # Patch the CoreDNS ConfigMap to add the custom domain forwarding
  local COREFILE_PATCH
  COREFILE_PATCH=$(printf '%s:53 {\n    errors\n    cache 30\n    forward . %s\n}\n' "$DTS_DOMAIN" "$DTS_FORWARD_IP")

  kubectl get configmap coredns -n kube-system -o json | \
  jq --arg patch "$COREFILE_PATCH" '.data.Corefile += $patch' | \
  kubectl apply -f -

  echo "CoreDNS ConfigMap patched. Restarting CoreDNS pods to apply changes..."
  kubectl rollout restart deployment coredns -n kube-system
  echo "CoreDNS pods are restarting."
}

install_metrics_server() {
  echo "✅ 6. Installing Metrics Server..."
  kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
  echo "Metrics Server installation initiated. It may take a minute to become available."
}

# --- Main Execution ---
main() {
  echo "🚀 Starting EKS Cluster Configuration Script..."

  # Prerequisite checks
  check_command "aws"
  check_command "kubectl"
  check_command "helm"
  check_command "jq"
  check_command "openssl"

  # Execute functions
  configure_kubeconfig
  setup_kubectl_autocomplete
  install_dashboard
  install_nginx_and_ssl
  configure_coredns
  install_metrics_server

  echo -e "\n🎉 Script finished successfully!"
}

main
