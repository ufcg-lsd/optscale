#!/bin/bash
set -eo pipefail

#================================================================================
# Configuration (defaults - can be overridden by args)
#================================================================================
EKS_CLUSTER_NAME="optscale-cluster"
AWS_REGION="us-east-1"
CONFIGURE_DTS_DOMAIN=true
DTS_DOMAIN="dts.loc"
DTS_FORWARD_IP="172.22.1.2"

# TLS defaults
TLS_SECRET_NAMESPACE="default"
TLS_SECRET_NAME="defaultcert"
TLS_CERT_PATH=""
TLS_KEY_PATH=""

#================================================================================
# Args / Help
#================================================================================
usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --cluster-name NAME         EKS cluster name (default: ${EKS_CLUSTER_NAME})
  --region REGION             AWS region (default: ${AWS_REGION})

  --tls-cert PATH             Path to TLS certificate file (PEM/CRT)
  --tls-key PATH              Path to TLS private key file (PEM)

  --tls-secret-name NAME      Kubernetes TLS secret name (default: ${TLS_SECRET_NAME})
  --tls-secret-namespace NS   Kubernetes namespace for the secret (default: ${TLS_SECRET_NAMESPACE})

  --configure-dts true|false  Configure CoreDNS forward for custom domain (default: ${CONFIGURE_DTS_DOMAIN})
  --dts-domain DOMAIN         Domain to forward (default: ${DTS_DOMAIN})
  --dts-forward-ip IP         Upstream DNS IP (default: ${DTS_FORWARD_IP})

  -h, --help                  Show this help and exit

Notes:
- You MUST provide both --tls-cert and --tls-key. The script will not generate a certificate.
- The provided secret will be referenced by the NGINX Ingress Controller via
  --set extraArgs.default-ssl-certificate=\${TLS_SECRET_NAMESPACE}/\${TLS_SECRET_NAME}.
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
    --configure-dts)          CONFIGURE_DTS_DOMAIN="$2"; shift 2 ;;
    --dts-domain)             DTS_DOMAIN="$2"; shift 2 ;;
    --dts-forward-ip)         DTS_FORWARD_IP="$2"; shift 2 ;;
    -h|--help)                usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

#================================================================================
# Helpers
#================================================================================
check_command() {
  if ! command -v "$1" &> /dev/null; then
    echo "🚨 Error: command '$1' not found. Please install it and ensure it's in your PATH."
    exit 1
  fi
}

require_file() {
  local p="$1"
  local label="$2"
  if [[ -z "$p" ]]; then
    echo "🚨 Error: missing $label path. Use --$label <path>."
    exit 1
  fi
  if [[ ! -f "$p" ]]; then
    echo "🚨 Error: $label '$p' not found or not a file."
    exit 1
  fi
}

#================================================================================
# Main functions
#================================================================================
configure_kubeconfig() {
  echo "✅ 1. Configuring kubeconfig for EKS cluster '$EKS_CLUSTER_NAME' in '$AWS_REGION'..."
  aws eks update-kubeconfig --name "$EKS_CLUSTER_NAME" --region "$AWS_REGION"
  echo "Kubeconfig updated successfully."
}

setup_kubectl_autocomplete() {
  echo "✅ 2. Setting up kubectl bash autocompletion..."
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
  echo "✅ 3. Installing Kubernetes Dashboard..."
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml
  echo "Dashboard deployment initiated."
}

install_nginx_and_ssl() {
  echo "✅ 4. Using provided TLS key/cert and installing NGINX Ingress..."

  # Validate inputs
  require_file "$TLS_CERT_PATH" "tls-cert"
  require_file "$TLS_KEY_PATH"  "tls-key"

  echo "-> Ensuring namespace '$TLS_SECRET_NAMESPACE' exists..."
  kubectl get ns "$TLS_SECRET_NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$TLS_SECRET_NAMESPACE"

  echo "-> Creating/updating TLS secret '$TLS_SECRET_NAME' in namespace '$TLS_SECRET_NAMESPACE'..."
  if kubectl -n "$TLS_SECRET_NAMESPACE" get secret "$TLS_SECRET_NAME" >/dev/null 2>&1; then
    kubectl -n "$TLS_SECRET_NAMESPACE" delete secret "$TLS_SECRET_NAME"
  fi
  kubectl -n "$TLS_SECRET_NAMESPACE" create secret tls "$TLS_SECRET_NAME" \
    --cert "$TLS_CERT_PATH" \
    --key "$TLS_KEY_PATH"

  echo "-> Adding and updating the Bitnami Helm repository..."
  if ! helm repo list | grep -q "ingress-nginx"; then
    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
  fi
  helm repo update

  # Deploys nginx receiving the ssl key passed as argument
  # Configure LoadBalancer to only accept requests from LSD's Nat
  echo "-> Installing/Upgrading NGINX Ingress Controller (ingress-nginx)..."
  helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --set controller.hostNetwork=true \
  --set controller.kind=DaemonSet \
  --set controller.daemonset.useHostPort=true \
  --set controller.extraArgs.default-ssl-certificate="${TLS_SECRET_NAMESPACE}/${TLS_SECRET_NAME}" \
  --set controller.resources.requests.memory=384Mi \
  --set controller.resources.limits.memory=896Mi \
  --set controller.service.type=LoadBalancer \
  --set-json 'controller.service.loadBalancerSourceRanges=["10.251.0.0/16"]'

  echo "NGINX Ingress is configured to use TLS secret '${TLS_SECRET_NAMESPACE}/${TLS_SECRET_NAME}'."
}

configure_coredns() {
  if [[ "$CONFIGURE_DTS_DOMAIN" != "true" ]]; then
    echo "☑️ 5. Skipping CoreDNS configuration."
    return
  fi

  echo "✅ 5. Configuring CoreDNS to forward '$DTS_DOMAIN' to '$DTS_FORWARD_IP'..."
  local corefile
  corefile="$(kubectl get configmap coredns -n kube-system -o jsonpath='{.data.Corefile}')"

  if grep -qE "^[[:space:]]*${DTS_DOMAIN}:" <<< "$corefile"; then
    echo "CoreDNS already configured for $DTS_DOMAIN. Skipping."
    return
  fi

  local COREFILE_PATCH
  COREFILE_PATCH=$(printf '%s:53 {\n    errors\n    cache 30\n    forward . %s\n}\n' "$DTS_DOMAIN" "$DTS_FORWARD_IP")

  kubectl get configmap coredns -n kube-system -o json | \
    jq --arg patch "$COREFILE_PATCH" '.data.Corefile += $patch' | \
    kubectl apply -f -

  echo "Restarting CoreDNS to apply changes..."
  kubectl rollout restart deployment coredns -n kube-system
}

label_current_node() {
  echo "✅ 6. Labeling the current node (first Ready node) with node-role.kubernetes.io/control-plane=\"\" ..."

  if ! kubectl get --raw='/readyz' >/dev/null 2>&1; then
    echo "🚨 kubectl can’t reach the API server (readyz check failed)."
    kubectl config current-context || true
    exit 1
  fi

  NODE_NAME="$(
    kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.conditions[?(@.type=="Ready")]}{.status}{"\n"}{end}{end}' \
    | awk '$2=="True"{print $1; exit}'
  )"
  if [[ -z "$NODE_NAME" ]]; then
    echo "🚨 No Ready nodes found."
    exit 1
  fi

  echo "-> Target node: $NODE_NAME"
  if ! kubectl label node "$NODE_NAME" node-role.kubernetes.io/control-plane="" --overwrite; then
    echo "⚠️  Labeling failed. Common causes:"
    echo "   - RBAC: your identity lacks permissions to list/patch nodes."
    echo "   - Admission/PSA: cluster policy blocks labeling nodes."
    echo "   - Managed clusters: non-admin users can’t mutate Node objects."
    exit 1
  fi

  echo "🎉 Labeled $NODE_NAME with node-role.kubernetes.io/control-plane=\"\""
}

#================================================================================
# Main
#================================================================================
main() {
  echo "🚀 Starting EKS Cluster Configuration Script..."
  check_command "aws"
  check_command "kubectl"
  check_command "helm"
  check_command "jq"
  check_command "openssl"

  configure_kubeconfig
  setup_kubectl_autocomplete
  install_dashboard
  install_nginx_and_ssl
  configure_coredns
  label_current_node

  helm upgrade --install -f values-teste.yaml optscale ./optscale/

  echo -e "\n🎉 Script finished successfully!"
  echo "ℹ️ Default SSL certificate in NGINX Ingress: ${TLS_SECRET_NAMESPACE}/${TLS_SECRET_NAME}"
}

main

