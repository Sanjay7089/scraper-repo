#!/bin/bash
# test.sh - Test FAQ Scraper Lambda function
# Usage: ./test.sh --region us-east-1 --account 304598107598 --profile access-role

set -e

# Default Configuration
FUNCTION_NAME="scraper-with-docker"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
REGION="us-east-1"
ACCOUNT="304598107598"
PROFILE="access-role"

# Function to display usage
usage() {
    echo "Usage: $0 --region REGION --account ACCOUNT --profile PROFILE [OPTIONS]"
    echo ""
    echo "Required Parameters:"
    echo "  --region REGION          AWS region (e.g., us-east-1)"
    echo "  --account ACCOUNT        AWS account ID (12-digit number)"
    echo "  --profile PROFILE        AWS CLI profile name"
    echo ""
    echo "Optional Parameters:"
    echo "  --function-name NAME     Lambda function name (default: $FUNCTION_NAME)"
    echo "  --help                   Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 --region us-east-1 --account 304598107598 --profile access-role"
}

echo_info() {
    echo -e "${GREEN}ℹ️  $1${NC}"
}

echo_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

echo_error() {
    echo -e "${RED}❌ $1${NC}"
}

echo_step() {
    echo -e "${BLUE}🔄 $1${NC}"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --region)
            REGION="$2"
            shift 2
            ;;
        --account)
            ACCOUNT="$2"
            shift 2
            ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --function-name)
            FUNCTION_NAME="$2"
            shift 2
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            echo_error "Unknown parameter: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$REGION" || -z "$ACCOUNT" || -z "$PROFILE" ]]; then
    echo_error "Missing required parameters"
    usage
    exit 1
fi

# Set AWS CLI parameters
AWS_CMD="aws --profile $PROFILE --region $REGION"

echo_info "🧪 FAQ Scraper Lambda Test"
echo "====================================="
echo_info "Function Name: $FUNCTION_NAME"
echo_info "Region: $REGION"
echo_info "Account: $ACCOUNT"
echo_info "Profile: $PROFILE"
echo "====================================="

# Step 1: Validate AWS CLI and Profile
echo_step "Step 1: Validating AWS Configuration"

if ! $AWS_CMD sts get-caller-identity &>/dev/null; then
    echo_error "AWS CLI not configured properly or profile '$PROFILE' not found"
    echo "Please check your AWS CLI configuration and profile"
    exit 1
fi

CURRENT_ACCOUNT=$($AWS_CMD sts get-caller-identity --query 'Account' --output text)
if [[ "$CURRENT_ACCOUNT" != "$ACCOUNT" ]]; then
    echo_error "Account mismatch! Expected: $ACCOUNT, Got: $CURRENT_ACCOUNT"
    exit 1
fi

echo_info "AWS CLI configured correctly ✅"

# Step 2: Check if Function Exists
echo_step "Step 2: Checking Lambda Function"

if ! $AWS_CMD lambda get-function --function-name $FUNCTION_NAME &>/dev/null; then
    echo_error "Function '$FUNCTION_NAME' not found in region $REGION"
    echo "Please deploy the function first using deploy.sh"
    exit 1
fi

echo_info "Lambda function exists ✅"

# Step 3: Test Lambda Function
echo_step "Step 3: Testing Lambda Function"

# Create test payload
cat > test_payload.json <<EOF
{
    "url": "https://mycash.utah.gov/app/faq-general"
}
EOF

echo_info "Invoking Lambda function..."
sleep 5  # Wait for function to stabilize

# Invoke function
INVOKE_RESULT=$($AWS_CMD lambda invoke \
    --function-name $FUNCTION_NAME \
    --cli-binary-format raw-in-base64-out \
    --payload file://test_payload.json \
    --log-type Tail \
    response.json \
    --query 'StatusCode' \
    --output text)

if [[ "$INVOKE_RESULT" == "200" ]]; then
    echo_info "✅ Lambda function test PASSED!"
    
    # Parse response
    if command -v jq &>/dev/null; then
        SUCCESS=$(jq -r '.body | fromjson | .success' response.json 2>/dev/null || echo "unknown")
        FAQ_COUNT=$(jq -r '.body | fromjson | .count' response.json 2>/dev/null || echo "unknown")
        echo_info "Success: $SUCCESS"
        echo_info "Extracted $FAQ_COUNT FAQs"
        
        SAMPLE_FAQ=$(jq -r '.body | fromjson | .data[0] | "Q: " + .question + "\nA: " + (.answer[:100] + "...")' response.json 2>/dev/null || echo "Could not parse FAQ")
        echo_info "Sample FAQ:\n$SAMPLE_FAQ"
    else
        echo_warning "Install 'jq' to see detailed response parsing"
        echo_info "Raw response in response.json"
    fi
else
    echo_error "Lambda function test FAILED!"
    echo "Check response.json for details"
    if [[ -f response.json ]]; then
        cat response.json
    fi
fi



echo ""
echo_info "🎉 Testing Complete!"
echo "==========================================="
echo_info "Function Name: $FUNCTION_NAME"
echo_info "Function ARN: arn:aws:lambda:$REGION:$ACCOUNT:function:$FUNCTION_NAME"
echo_info "Region: $REGION"
echo "==========================================="