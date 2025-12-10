#!/bin/bash
set -eo pipefail

#================================================================================
# Configuration (defaults - can be overridden by args)
#================================================================================
EKS_CLUSTER_NAME=
AWS_REGION="us-east-1"

# TLS defaults
TLS_SECRET_NAMESPACE="default"
TLS_SECRET_NAME="defaultcert"
TLS_CERT_PATH=""
TLS_KEY_PATH=""
TLS_OUTPUT_DIR="./tmp_tls"
TLS_CERT_DEFAULT="${TLS_OUTPUT_DIR}/optscale.crt"
TLS_KEY_DEFAULT="${TLS_OUTPUT_DIR}/optscale.key"

#================================================================================
# Args / Help
#================================================================================
usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --cluster-name NAME         (REQUIRED) EKS cluster name
  --region REGION             AWS region (default: ${AWS_REGION})

  --tls-cert PATH             Path to TLS certificate file (PEM/CRT)
  --tls-key PATH              Path to TLS private key file (PEM)

  --tls-secret-name NAME      Kubernetes TLS secret name (default: ${TLS_SECRET_NAME})
  --tls-secret-namespace NS   Kubernetes namespace for the secret (default: ${TLS_SECRET_NAMESPACE})

  -h, --help                  Show this help and exit

Behavior:
- If BOTH --tls-cert and --tls-key are provided, they will be used as-is.
- If NEITHER is provided, a self-signed localhost cert/key will be created at:
    ${TLS_CERT_DEFAULT}
    ${TLS_KEY_DEFAULT}
  and used automatically.
- If only one of --tls-cert/--tls-key is provided, the script exits with an error.

NGINX Ingress will be configured with:
  --set controller.extraArgs.default-ssl-certificate=\${TLS_SECRET_NAMESPACE}/\${TLS_SECRET_NAME}

Helm 'optscale' install will pass the key/cert via:
  --set-file optscale_key=<key> --set-file certificates.optscale=<cert>
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cluster-name)           EKS_CLUSTER_NAME="$2"; shift 2 ;;
    --region)                 AWS_REGION="$2"; shift 2 ;;
    --tls-cert)               TLS_CERT_PATH="$2"; shift 2 ;;
    --tls-key)                TLS_KEY_PATH="$2"; shift 2 ;;
    --tls-secret-name)        TLS_SECRET_NAME="$2"; shift 2 ;;
    --tls-secret-namespace)   TLS_SECRET_NAMESPACE="$2"; shift 2 ;;
    -h|--help)                usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

#================================================================================
# Helpers
#================================================================================
error() { echo "🚨 $*" >&2; exit 1; }

check_command() {
  if ! command -v "$1" &> /dev/null; then
    error "Error: command '$1' not found. Please install it and ensure it's in your PATH."
  fi
}

require_file() {
  local p="$1"
  local label="$2"
  [[ -n "$p" ]] || error "Missing $label path."
  [[ -f "$p" ]] || error "$label '$p' not found or not a file."
}

ensure_required_inputs() {
  [[ -n "$EKS_CLUSTER_NAME" ]] || { usage; error "You must provide --cluster-name."; }

  # TLS logic: both provided, or none (auto-create). Not allowed: only one.
  if [[ -n "$TLS_CERT_PATH" || -n "$TLS_KEY_PATH" ]]; then
    if [[ -z "$TLS_CERT_PATH" || -z "$TLS_KEY_PATH" ]]; then
      error "Provide BOTH --tls-cert and --tls-key, or neither to auto-generate."
    fi
  fi
}

generate_localhost_tls_if_needed() {
  # If both provided, just validate and return.
  if [[ -n "$TLS_CERT_PATH" && -n "$TLS_KEY_PATH" ]]; then
    require_file "$TLS_CERT_PATH" "tls-cert"
    require_file "$TLS_KEY_PATH"  "tls-key"
    echo "Using provided TLS materials:"
    echo "    cert: $TLS_CERT_PATH"
    echo "    key : $TLS_KEY_PATH"
    return
  fi

  # Neither provided — generate self-signed cert/key to ./tmp_tls/optscale.*
  echo "No TLS provided. Generating self-signed localhost certificate/key..."
  check_command "openssl"

  mkdir -p "${TLS_OUTPUT_DIR}"

  echo "-> Creating OpenSSL configuration file for localhost..."
  cat <<'EOF' > /tmp/openssl.cfg
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

  # Generate key and cert
  openssl req -x509 -nodes -newkey rsa:2048 \
    -days 365 \
    -keyout "${TLS_KEY_DEFAULT}" \
    -out "${TLS_CERT_DEFAULT}" \
    -config /tmp/openssl.cfg \
    -extensions v3_req

  chmod 600 "${TLS_KEY_DEFAULT}" || true

  TLS_CERT_PATH="${TLS_CERT_DEFAULT}"
  TLS_KEY_PATH="${TLS_KEY_DEFAULT}"

  echo "Generated:"
  echo "    cert: ${TLS_CERT_PATH}"
  echo "    key : ${TLS_KEY_PATH}"
}

#================================================================================
# Main functions
#================================================================================
configure_kubeconfig() {
  echo "1. Configuring kubeconfig for EKS cluster '$EKS_CLUSTER_NAME' in '$AWS_REGION'..."
  aws eks update-kubeconfig --name "$EKS_CLUSTER_NAME" --region "$AWS_REGION"
  echo "Kubeconfig updated successfully."
}

setup_kubectl_autocomplete() {
  echo "2. Setting up kubectl bash autocompletion..."
  local BASHRC_PATH="$HOME/.bashrc"
  local AUTOCOMPLETE_LINE='source <(kubectl completion bash)'
  if ! grep -Fxq "$AUTOCOMPLETE_LINE" "$BASHRC_PATH" 2>/dev/null; then
    echo "$AUTOCOMPLETE_LINE" >> "$BASHRC_PATH"
    echo "Autocompletion added to $BASHRC_PATH. Run 'source ~/.bashrc' or restart your shell."
  else
    echo "Autocompletion already configured."
  fi
}

install_dashboard() {
  echo "3. Installing Kubernetes Dashboard..."
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml
  echo "Dashboard deployment initiated."
}

install_nginx_and_ssl() {
  echo "4. Using TLS key/cert and installing NGINX Ingress..."

  # Validate inputs (at this point either provided or generated)
  require_file "$TLS_CERT_PATH" "tls-cert"
  require_file "$TLS_KEY_PATH" "tls-key"

  echo "-> Ensuring namespace '$TLS_SECRET_NAMESPACE' exists..."
  kubectl get ns "$TLS_SECRET_NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$TLS_SECRET_NAMESPACE"

  echo "-> Creating/updating TLS secret '$TLS_SECRET_NAME' in namespace '$TLS_SECRET_NAMESPACE'..."
  if kubectl -n "$TLS_SECRET_NAMESPACE" get secret "$TLS_SECRET_NAME" >/dev/null 2>&1; then
    kubectl -n "$TLS_SECRET_NAMESPACE" delete secret "$TLS_SECRET_NAME"
  fi
  kubectl -n "$TLS_SECRET_NAMESPACE" create secret tls "$TLS_SECRET_NAME" \
    --cert "$TLS_CERT_PATH" \
    --key "$TLS_KEY_PATH"

  echo "-> Adding and updating the ingress-nginx Helm repository..."
  if ! helm repo list | grep -q "ingress-nginx"; then
    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
  fi
  helm repo update

  echo "-> Installing/Upgrading NGINX Ingress Controller (ingress-nginx)..."
  helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
    --set controller.hostNetwork=true \
    --set controller.kind=DaemonSet \
    --set controller.daemonset.useHostPort=true \
    --set controller.extraArgs.default-ssl-certificate="${TLS_SECRET_NAMESPACE}/${TLS_SECRET_NAME}" \
    --set controller.resources.requests.memory=384Mi \
    --set controller.resources.limits.memory=896Mi \
    --set controller.service.type=LoadBalancer \
    --set-json 'controller.service.loadBalancerSourceRanges=["150.165.15.3/25", "150.165.85.0/24", "150.165.75.242/32", "150.165.75.244/32", "10.1.4.0/24"]'

  echo "NGINX Ingress is configured to use TLS secret '${TLS_SECRET_NAMESPACE}/${TLS_SECRET_NAME}'."
}

label_current_node() {
  echo "5. Labeling nodes: one as control-plane and, if possible, another as mongo-node=true ..."

  if ! kubectl get --raw='/readyz' >/dev/null 2>&1; then
    echo "kubectl can’t reach the API server (readyz check failed)."
    kubectl config current-context || true
    exit 1
  fi

  # Get all Ready nodes into an array
  mapfile -t READY_NODES < <(
    kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.conditions[?(@.type=="Ready")]}{.status}{"\n"}{end}{end}' \
      | awk '$2=="True"{print $1}'
  )

  if ((${#READY_NODES[@]} == 0)); then
    error "No Ready nodes found."
  fi

  # First Ready node -> control-plane
  CONTROL_NODE="${READY_NODES[0]}"
  echo "-> Control-plane target node: ${CONTROL_NODE}"

  if ! kubectl label node "${CONTROL_NODE}" node-role.kubernetes.io/control-plane="" --overwrite; then
    echo "⚠️  Labeling control-plane failed. Common causes:"
    echo "   - RBAC: your identity lacks permissions to list/patch nodes."
    echo "   - Admission/PSA: cluster policy blocks labeling nodes."
    echo "   - Managed clusters: non-admin users can’t mutate Node objects."
    exit 1
  fi

  echo "Labeled ${CONTROL_NODE} with node-role.kubernetes.io/control-plane=\"\""

  # If there are 2+ Ready nodes, pick another one for mongo-node=true
  if ((${#READY_NODES[@]} >= 2)); then
    local MONGO_NODE=""
    # Prefer a node different from the control-plane node
    for n in "${READY_NODES[@]}"; do
      if [[ "$n" != "${CONTROL_NODE}" ]]; then
        MONGO_NODE="$n"
        break
      fi
    done

    if [[ -n "$MONGO_NODE" ]]; then
      echo "-> Mongo target node: ${MONGO_NODE}"
      if ! kubectl label node "${MONGO_NODE}" mongo-node=true --overwrite; then
        echo "⚠️  Labeling mongo-node failed. Common causes:"
        echo "   - RBAC: your identity lacks permissions to list/patch nodes."
        echo "   - Admission/PSA: cluster policy blocks labeling nodes."
        echo "   - Managed clusters: non-admin users can’t mutate Node objects."
        exit 1
      fi
      echo "Labeled ${MONGO_NODE} with mongo-node=true"
    else
      echo "⚠️  Could not find a different Ready node to label as mongo-node=true."
    fi
  else
    echo "Only one Ready node detected. Skipping mongo-node=true label."
  fi
}

main() {
  echo "Starting EKS Cluster Configuration Script..."
  check_command "aws"
  check_command "kubectl"
  check_command "helm"
  check_command "jq"
  check_command "openssl"

  ensure_required_inputs
  generate_localhost_tls_if_needed

  configure_kubeconfig
  setup_kubectl_autocomplete
  install_dashboard
  install_nginx_and_ssl
  label_current_node

  echo "Deploying 'optscale' with TLS files to Helm values..."
  helm upgrade --install \
    -f ./optscale/values-eks.yaml \
    --set-file optscale_key="${TLS_KEY_PATH}" \
    --set-file certificates.optscale="${TLS_CERT_PATH}" \
    optscale ./optscale/

  echo -e "\nScript finished successfully!"
  echo "ℹ️ Default SSL certificate in NGINX Ingress: ${TLS_SECRET_NAMESPACE}/${TLS_SECRET_NAME}"
  echo "TLS in use:"
  echo "    cert: ${TLS_CERT_PATH}"
  echo "    key : ${TLS_KEY_PATH}"
}

main

